"""Tool: analyze_image / analyze_pid

Local vision tool backed by the on-machine Qwen2.5-VL-3B-Instruct GGUF model
served through llama.cpp (OpenAI-compatible /v1 endpoint, localhost only).

Design rules (Sovereign AI):
  * Vision inference is ALWAYS local. The tool refuses to talk to any non-loopback
    endpoint and the agent run is additionally wrapped in a NetworkGuard.
  * The tool may only read files inside APPROVED_VISION_DIRS (path allow-list),
    preventing arbitrary filesystem access and leakage of .env / credentials /
    SSH keys / unrelated directories.
  * The model is treated as a *witness*, not as engineering truth. Output is
    structured and uncertainty is preserved. The model is forbidden from
    inventing tags / pressures / temperatures / specs. Unreadable items are
    labelled ``uncertain`` / ``not_visible`` / ``conflict``.
  * Supported inputs: JPG/PNG/... raster images, PDF pages (rendered to images),
    scanned documents, P&ID drawings, photographs, engineering drawings.

Returns a structured dict:
    {
      "file": str, "analysis_type": str, "description": str,
      "findings": list, "entities": list, "uncertain_items": list,
      "confidence": float, "model": str, "data_origin": "local",
      "timestamp": str, "source_file": str,         # provenance preserved
      "pages": list, "structured": dict,            # optional extras
    }
"""
import base64
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

import fitz  # PyMuPDF — local PDF text extraction + page rendering

from agent.config import (
    VISION_ENDPOINT,
    VISION_MODEL_NAME,
    VISION_TIMEOUT,
    APPROVED_VISION_DIRS,
    SUPPORTED_VISION_EXT,
    PDF_TEXT_MIN_CHARS,
    PDF_MAX_PAGES,
    VISION_MAX_EDGE,
    is_path_approved,
)
from agent.utils import now_iso

logger = logging.getLogger(__name__)

# Status labels the model is instructed to use for every extracted element.
_STATUS_LABELS = ("verified", "probable", "uncertain", "not_visible", "conflict")


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------
def validate_path(file_path: str) -> Path:
    """Resolve and authorize a vision input path. Raises on missing/denied."""
    if not file_path:
        raise ValueError("file_path is required")
    p = Path(file_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Vision input not found: {p}")
    if p.is_dir():
        raise IsADirectoryError(f"Vision input is a directory, not a file: {p}")
    if p.suffix.lower() not in SUPPORTED_VISION_EXT:
        raise ValueError(
            f"Unsupported vision input type '{p.suffix}'. "
            f"Supported: {sorted(SUPPORTED_VISION_EXT)}"
        )
    if not is_path_approved(p):
        raise PermissionError(
            f"Path outside approved local directories: {p}. "
            f"Vision tool may only read approved project paths."
        )
    return p


# ---------------------------------------------------------------------------
# Local endpoint guard
# ---------------------------------------------------------------------------
def _assert_local_endpoint(url: str) -> None:
    """Refuse to send image bytes to any non-loopback / non-private endpoint."""
    from urllib.parse import urlparse
    import ipaddress

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1", "ip6-localhost"):
        return
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_private:
            return
    except ValueError:
        # Unresolved hostname — do not trust (could require DNS / external net).
        raise ConnectionError(
            f"Vision endpoint host '{host}' is not a known local address. "
            f"Vision inference must remain local."
        )
    raise ConnectionError(
        f"Vision endpoint '{url}' is not loopback/private. "
        f"Vision inference must remain local (sovereignty)."
    )


# ---------------------------------------------------------------------------
# Image / PDF handling
# ---------------------------------------------------------------------------
def _encode_image_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _read_file_b64(path: Path) -> str:
    return _encode_image_bytes(path.read_bytes())


def _resize_image_b64(path: Path, max_edge: int = VISION_MAX_EDGE) -> str:
    """Read a raster image, downscale so its longest edge <= max_edge, return JPEG b64.

    Reduces CLIP image-encoding cost (which dominates CPU latency) while keeping
    the whole drawing visible to the VLM.
    """
    from PIL import Image

    img = Image.open(path)
    img = img.convert("RGB")
    w, h = img.size
    longest = max(w, h)
    if longest > max_edge:
        scale = max_edge / float(longest)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return _encode_image_bytes(buf.getvalue())


def pdf_has_sufficient_text(path: Path, min_chars: int = PDF_TEXT_MIN_CHARS) -> bool:
    """Return True if the PDF already contains extractable text worth using."""
    try:
        doc = fitz.open(str(path))
        try:
            text = "".join(page.get_text() or "" for page in doc)
        finally:
            doc.close()
        return len(text.strip()) >= min_chars
    except Exception as e:  # pragma: no cover - fall back to vision
        logger.warning("PDF text check failed for %s: %s", path, e)
        return False


def render_pdf_pages(path: Path, max_pages: int = PDF_MAX_PAGES) -> List[Dict[str, Any]]:
    """Render up to ``max_pages`` PDF pages to base64 JPEG images.

    Pages are downscaled so the longest edge is <= VISION_MAX_EDGE to keep local
    CLIP image-encoding latency practical.
    """
    pages: List[Dict[str, Any]] = []
    doc = fitz.open(str(path))
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = fitz.Pixmap(pix)
            import io
            from PIL import Image
            png = io.BytesIO(pix.tobytes("png"))
            im = Image.open(png).convert("RGB")
            w, h = im.size
            longest = max(w, h)
            if longest > VISION_MAX_EDGE:
                scale = VISION_MAX_EDGE / float(longest)
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=85)
            pages.append({"page": i + 1, "b64": _encode_image_bytes(buf.getvalue())})
    finally:
        doc.close()
    return pages


def extract_pdf_text(path: Path) -> str:
    """Extract concatenated text from a PDF (preserves nothing else)."""
    try:
        doc = fitz.open(str(path))
        try:
            return "\n".join(page.get_text() or "" for page in doc).strip()
        finally:
            doc.close()
    except Exception as e:  # pragma: no cover
        logger.warning("PDF text extraction failed for %s: %s", path, e)
        return ""


# ---------------------------------------------------------------------------
# VLM call (local OpenAI-compatible server)
# ---------------------------------------------------------------------------
def _call_vlm(content: List[Dict[str, Any]], max_tokens: int = 600) -> str:
    """Send a single user message (text + optional images) to the local VLM.

    Returns the model text. Raises on connection / generation failure.
    """
    _assert_local_endpoint(VISION_ENDPOINT)
    from openai import OpenAI

    client = OpenAI(base_url=VISION_ENDPOINT, api_key="none", timeout=VISION_TIMEOUT)
    resp = client.chat.completions.create(
        model=VISION_MODEL_NAME,
        messages=[{"role": "user", "content": content}],
        max_tokens=max_tokens,
        temperature=0.1,
    )
    return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Prompt builders (each demands structured, uncertainty-aware output)
# ---------------------------------------------------------------------------
def _pid_prompt() -> str:
    return (
        "You are inspecting a Piping & Instrumentation Diagram (P&ID). "
        "Reply with ONE compact JSON object only (no prose, no markdown). Keep EVERY array "
        "short (at most 10 items). Only list equipment/tags you can CLEARLY read. "
        "If something is unreadable, write the string 'uncertain'. NEVER invent tag numbers, "
        "pressures, temperatures or specifications. Schema:\n"
        "{\n"
        '  "plant_system": "<short phrase (verified|probable|uncertain)>",\n'
        '  "equipment": ["<name (status)>"],\n'
        '  "equipment_tags": ["<tag (status)>"],\n'
        '  "pumps": ["<tag/name (status)>"], "vessels": ["<tag/name (status)>"],\n'
        '  "reactors": ["<tag/name (status)>"], "valves": ["<tag/name (status)>"],\n'
        '  "instruments": ["<tag/name (status)>"],\n'
        '  "process_streams": ["<desc + direction (status)>"],\n'
        '  "relationships": ["<visible relationship (status)>"],\n'
        '  "uncertain": ["<unreadable/ambiguous/conflict (uncertain|not_visible|conflict)>"]\n'
        "}\n"
        "Hard limit: AT MOST 8 items TOTAL across all arrays. If the drawing is dense, "
        "list only the few clearest items. If a category is absent use []. "
        "Stop immediately after the closing brace."
    )


def _document_prompt() -> str:
    return (
        "You are reading a scanned document / engineering page. "
        "Reply with ONE compact JSON object only (no prose, no markdown). Keep arrays short "
        "(<=8 items). Do not invent values; mark unreadable text as uncertain or not_visible. "
        "Schema:\n"
        "{\n"
        '  "description": "<concise summary>",\n'
        '  "findings": ["<key fact (verified|probable|uncertain)>"],\n'
        '  "entities": ["<named entity (status)>"],\n'
        '  "uncertain_items": ["<unreadable/ambiguous (uncertain|not_visible|conflict)>"]\n'
        "}\n"
        "Stop immediately after the closing brace."
    )


def _general_prompt() -> str:
    return (
        "You are describing an image for an engineering audit. "
        "Reply with ONE compact JSON object only (no prose, no markdown). Keep arrays short "
        "(<=8 items). Do not invent information; mark the unreadable as uncertain or not_visible. "
        "Schema:\n"
        "{\n"
        '  "description": "<concise description>",\n'
        '  "findings": ["<observable fact (verified|probable|uncertain)>"],\n'
        '  "entities": ["<named object/equipment/tag (status)>"],\n'
        '  "uncertain_items": ["<unclear item (uncertain|not_visible|conflict)>"]\n'
        "}\n"
        "Stop immediately after the closing brace."
    )


def _ocr_prompt() -> str:
    return (
        "Transcribe the text visible in this image. Reply with ONE compact JSON object only "
        "(no prose, no markdown). Transcribe only what is legible; never guess missing characters. "
        "Schema:\n"
        "{\n"
        '  "description": "<document type>",\n'
        '  "transcription": "<verbatim text; if unreadable say uncertain>",\n'
        '  "findings": ["<useful fact (verified|probable|uncertain)>"],\n'
        '  "entities": ["<named entity (status)>"],\n'
        '  "uncertain_items": ["<unreadable parts (uncertain|not_visible)>"]\n'
        "}\n"
        "Stop immediately after the closing brace."
    )


_PROMPTS = {
    "pid": _pid_prompt,
    "document": _document_prompt,
    "doc": _document_prompt,
    "ocr": _ocr_prompt,
    "inspection": _general_prompt,
    "general": _general_prompt,
}


def build_prompt(analysis_type: str, user_prompt: Optional[str] = None) -> str:
    base = _PROMPTS.get((analysis_type or "general").lower(), _general_prompt)()
    if user_prompt:
        return f"{user_prompt}\n\nStructured extraction requirements:\n{base}"
    return base


# ---------------------------------------------------------------------------
# Output parsing + structuring
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort extraction of the first JSON object from model output.

    Handles the common local-VLM failure modes:
      * markdown code fences,
      * trailing prose after the JSON,
      * truncated JSON (max_tokens cut off mid-object / mid-array).
    """
    if not text:
        return None
    # Strip markdown fences.
    cleaned = re.sub(r"```(?:json)?", "", text).strip()

    # 1) Whole thing is valid JSON.
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # 2) Find the first balanced {...} block (robust to trailing prose).
    start = cleaned.find("{")
    if start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(cleaned)):
            c = cleaned[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break

    # 3) Truncated JSON (no closing brace): take from first '{' to end of output
    #    and repair unterminated arrays/objects/strings.
    if start != -1:
        repaired = _repair_truncated(cleaned[start:])
        if repaired is not None:
            return repaired
    return None


def _repair_truncated(snippet: str) -> Optional[Dict[str, Any]]:
    """Close an unterminated JSON object/array (truncated by max_tokens)."""
    opens = {"{": "}", "[": "]"}
    stack = []
    in_str = False
    esc = False
    for c in snippet:
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in opens:
            stack.append(opens[c])
        elif c in ("}", "]"):
            if stack and stack[-1] == c:
                stack.pop()
    if not stack:
        return None
    repaired = snippet.rstrip()
    # Drop a trailing comma before closing.
    if repaired.endswith(","):
        repaired = repaired[:-1]
    # Close a dangling string value (odd number of quotes => unterminated).
    if repaired.count('"') % 2 == 1:
        repaired += '"'
    while stack:
        repaired += stack.pop()
    try:
        return json.loads(repaired)
    except Exception:
        return None


def _status_of(item: Any) -> str:
    """Infer the uncertainty status of a string/fact for the uncertain_items list."""
    s = str(item).lower()
    for label in ("conflict", "not_visible", "not visible", "uncertain"):
        if label in s:
            return label.replace(" ", "_")
    return "verified"


def _confidence(findings_n: int, uncertain_n: int) -> float:
    """Heuristic confidence: lower when more items are uncertain."""
    total = findings_n + uncertain_n
    if total == 0:
        return 0.3
    frac = uncertain_n / total
    conf = max(0.1, round(0.9 - 0.6 * frac, 2))
    return conf


def _structure_result(analysis_type: str, raw: Dict[str, Any], source_file: str,
                      prompt_used: str) -> Dict[str, Any]:
    """Map the model JSON into the canonical structured output schema."""
    at = (analysis_type or "general").lower()

    if at == "pid":
        description = raw.get("plant_system") or raw.get("description") or ""
        equipment = raw.get("equipment", []) or []
        tags = raw.get("equipment_tags", []) or []
        entities: List[Any] = []
        for grp in ("pumps", "vessels", "reactors", "valves", "instruments"):
            for e in (raw.get(grp, []) or []):
                entities.append({"type": grp, "name": str(e)})
        for t in tags:
            entities.append({"type": "equipment_tag", "name": str(t)})
        for eq in equipment:
            entities.append({"type": "equipment", "name": str(eq)})
        findings = (
            [f"Plant/system: {description}"] if description else []
        )
        findings += [f"Equipment: {e}" for e in equipment]
        findings += [f"Tag: {t}" for t in tags]
        streams = raw.get("process_streams", []) or []
        rels = raw.get("relationships", []) or []
        findings += [f"Process stream: {s}" for s in streams]
        findings += [f"Relationship: {r}" for r in rels]
        uncertain = raw.get("uncertain", []) or []
    else:
        description = raw.get("description") or raw.get("transcription") or ""
        entities = [{"type": "entity", "name": str(e)} for e in (raw.get("entities", []) or [])]
        findings = [str(f) for f in (raw.get("findings", []) or [])]
        if raw.get("transcription"):
            findings = [f"Transcription: {raw['transcription']}"] + findings
        uncertain = raw.get("uncertain_items", []) or []

    # Normalise everything to strings and keep the payload sane even when the
    # model ignored the JSON contract (failed parse -> free text).
    description = str(description)[:1500]
    findings = [str(f) for f in findings if f][:12]
    uncertain_items = [str(u) for u in uncertain if u][:12]

    conf = _confidence(len(findings), len(uncertain_items))

    return {
        "file": source_file,
        "analysis_type": at,
        "description": str(description),
        "findings": findings,
        "entities": entities,
        "uncertain_items": uncertain_items,
        "confidence": conf,
        "model": VISION_MODEL_NAME,
        "data_origin": "local",
        "timestamp": now_iso(),
        "source_file": source_file,
        "prompt": prompt_used,
        "structured": raw,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def analyze_image(
    file_path: str,
    prompt: Optional[str] = None,
    analysis_type: str = "general",
) -> Dict[str, Any]:
    """Analyze an image / PDF with the local Qwen-VL model.

    Returns the canonical structured dict. Raises on bad path, denied path, or
    VLM failure.
    """
    start = time.time()
    path = validate_path(file_path)
    at = (analysis_type or "general").lower()
    source_file = path.name

    if at == "pid":
        prompt_used = build_prompt("pid", prompt)
        content: List[Dict[str, Any]] = [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{_resize_image_b64(path)}"}},
            {"type": "text", "text": prompt_used},
        ]
        raw_text = _call_vlm(content, max_tokens=500)
        raw = _extract_json(raw_text)
        if raw is None:
            raw = {"description": "(VLM output was not valid JSON; raw text kept in structured.raw_text)",
                   "raw_text": raw_text, "findings": [],
                   "entities": [], "uncertain_items": ["model_output_not_json"]}
        result = _structure_result("pid", raw, source_file, prompt_used)
        result["pages"] = [{"page": 1, "source": source_file}]
        result["execution_time_s"] = round(time.time() - start, 3)
        return result

    if path.suffix.lower() == ".pdf":
        return _analyze_pdf(path, prompt, at, start)

    # Raster image (general / document / ocr / inspection).
    prompt_used = build_prompt(at, prompt)
    content = [
        {"type": "image_url",
         "image_url": {"url": f"data:image/jpeg;base64,{_resize_image_b64(path)}"}},
        {"type": "text", "text": prompt_used},
    ]
    raw_text = _call_vlm(content, max_tokens=450)
    raw = _extract_json(raw_text)
    if raw is None:
        raw = {"description": "(VLM output was not valid JSON; raw text kept in structured.raw_text)",
               "raw_text": raw_text, "findings": [],
               "entities": [], "uncertain_items": ["model_output_not_json"]}
    result = _structure_result(at, raw, source_file, prompt_used)
    result["pages"] = [{"page": 1, "source": source_file}]
    result["execution_time_s"] = round(time.time() - start, 3)
    return result


def _analyze_pdf(path: Path, prompt: Optional[str], at: str, start: float) -> Dict[str, Any]:
    """Scanned-document flow: prefer text, fall back to rendered pages + VLM."""
    source_file = path.name
    extracted_text = extract_pdf_text(path)
    sufficient = len(extracted_text.strip()) >= PDF_TEXT_MIN_CHARS

    pages_meta: List[Dict[str, Any]] = []
    raw_parts: List[Dict[str, Any]] = []

    if sufficient:
        # Text is enough — still ask the VLM to summarise/structure the text.
        prompt_used = build_prompt(at, prompt or "Summarise this document page.")
        content = [{"type": "text",
                    "text": f"{prompt_used}\n\nDOCUMENT TEXT:\n{extracted_text[:6000]}"}]
        raw_text = _call_vlm(content, max_tokens=450)
        raw = _extract_json(raw_text)
        if raw is None:
            raw = {"description": "(VLM output not valid JSON; raw text in structured.raw_text)",
                   "raw_text": raw_text}
        raw["_text_extracted"] = True
        raw_parts.append(raw)
        pages_meta.append({"page": "all", "source": source_file, "mode": "text"})
    else:
        # Insufficient text -> render pages and analyze each.
        rendered = render_pdf_pages(path, PDF_MAX_PAGES)
        if not rendered:
            raise ValueError(f"Could not render any pages from PDF: {path}")
        for pg in rendered:
            prompt_used = build_prompt(at, prompt)
            content = [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{pg['b64']}"}},
                {"type": "text", "text": prompt_used},
            ]
            raw_text = _call_vlm(content, max_tokens=450)
            raw = _extract_json(raw_text)
            if raw is None:
                raw = {"description": "(VLM output not valid JSON; raw text in structured.raw_text)",
                       "raw_text": raw_text}
            raw["_page"] = pg["page"]
            raw_parts.append(raw)
            pages_meta.append({"page": pg["page"], "source": source_file, "mode": "vision"})

    # Merge multiple page results.
    merged: Dict[str, Any] = {
        "description": " | ".join(str(p.get("description", "")) for p in raw_parts if p.get("description")),
        "findings": [],
        "entities": [],
        "uncertain_items": [],
        "transcription": "",
    }
    for p in raw_parts:
        merged["findings"] += list(p.get("findings", []) or [])
        merged["entities"] += list(p.get("entities", []) or [])
        merged["uncertain_items"] += list(p.get("uncertain_items", []) or [])
        if p.get("transcription"):
            merged["transcription"] += p["transcription"] + "\n"

    result = _structure_result(at, merged, source_file, build_prompt(at, prompt))
    result["pages"] = pages_meta
    result["text_extracted"] = sufficient
    result["execution_time_s"] = round(time.time() - start, 3)
    return result


def analyze_pid(file_path: str, prompt: Optional[str] = None) -> Dict[str, Any]:
    """Convenience wrapper for P&ID analysis."""
    return analyze_image(file_path, prompt=prompt, analysis_type="pid")


def extract_equipment_tags(result: Dict[str, Any]) -> List[str]:
    """Pull candidate equipment tags (R-1001, P-101, T-xxx, ...) from a result.

    Used by the agent to feed the RAG retriever from vision-extracted evidence.
    """
    tags: List[str] = []
    text = " ".join([
        result.get("description", ""),
        " ".join(str(f) for f in result.get("findings", [])),
        " ".join(str(e.get("name", "")) for e in result.get("entities", []) if isinstance(e, dict)),
    ])
    for m in re.findall(r"\b[A-Z]{1,3}-?\d{2,4}[A-Z]?\b", text):
        if m not in tags:
            tags.append(m)
    return tags
