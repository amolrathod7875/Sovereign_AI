"""Sovereign AI — unified local model router (capability-based).

This is the single decision layer that maps a user task onto the appropriate
LOCAL open-weight model(s). It is NOT an agent: it classifies task characteristics
along several independent dimensions, matches them against the capabilities
declared in ``app.models.registry``, and emits an explainable ``RoutingDecision``.

Design rules
------------
* Every model it may select is local (local=True + loopback/private endpoint).
* A complex task may legitimately require MORE THAN ONE model (e.g. vision for a
  P&ID plus general for RAG-grounded synthesis). ``models_required`` reflects that.
* If no local model satisfies a required capability, routing FAILS loudly — it
  never silently falls back to an external / cloud model.
* Routing is cheap (pure classification + dict lookup). It never invokes a large
  model merely to classify a request.

The legacy ``route_task(task_type, has_image)`` is kept for backward compatibility
with the existing ``POST /api/models/route`` surface and now delegates here.
"""
import logging
import time
import re
from typing import Dict, List, Optional

from app.schemas import TaskType, RoutingDecision, RoutingRequest
from app.models.registry import (
    get_model, get_local_models, get_models_with_capability,
    validate_local_endpoint, capability_label,
)

logger = logging.getLogger(__name__)


class NoLocalModelAvailable(Exception):
    """Raised when a required capability has no local model to serve it."""


# ---------------------------------------------------------------------------
# Multi-factor task classification
# ---------------------------------------------------------------------------
_VISION_INPUT_TOKENS = [
    "image", "picture", "photo", "drawing", "diagram", "p&id", "pid",
    "scan", "scanned", "pdf", "screenshot", "visual", "figure",
]
_VISION_INTENT_VERBS = [
    "identify", "analyze", "inspect", "read", "describe", "extract", "recognize",
    "detect", "what", "see", "look", "transcribe", "examine", "classify",
    "find", "locate",
]
_CODE_VERBS = [
    "write", "generate", "create", "implement", "code", "develop", "build",
    "debug", "fix", "refactor", "review", "script", "program", "calculate",
]
_CODE_NOUNS = [
    "python", "code", "function", "script", "class", "api", "algorithm", "sql",
    "program", "reynolds", "module", "unittest", "pytest", "decorator", "loop",
]
_RAG_NOUNS = [
    "manual", "sop", "maintenance", "procedure", "r-1001", "knowledge base",
    "documents", "document", "specification", "datasheet", "standard", "guideline",
    "report", "correspondence", "approval", "operating", "pm ", "inspection",
    "requirement", "requirements",
]


def classify_task(
    task: str,
    has_image: bool = False,
    image_path: str = None,
    requires_code: bool = None,
    requires_vision: bool = None,
    requires_rag: bool = None,
    requires_tools: bool = None,
    task_type: str = None,
    complexity: str = None,
) -> Dict:
    """Return a dict of task characteristics.

    Classification uses several INDEPENDENT signals; no single keyword decides the
    route. Explicit overrides (when the caller already knows the characteristics)
    take precedence.
    """
    text = (task or "").lower()
    has_image_input = bool(has_image) or bool(image_path) or any(
        t in text for t in _VISION_INPUT_TOKENS
    )

    # Vision: need an image AND an analysis intent (or explicit override).
    vision_intent = any(v in text for v in _VISION_INTENT_VERBS)
    if requires_vision is None:
        requires_vision = bool(has_image_input and vision_intent)
    else:
        requires_vision = bool(requires_vision)

    # Code: BOTH a code verb and a programming noun, or explicit override.
    code_verb = any(v in text for v in _CODE_VERBS)
    code_noun = any(n in text for n in _CODE_NOUNS)
    if requires_code is None:
        requires_code = bool(code_verb and code_noun)
    else:
        requires_code = bool(requires_code)

    # RAG: grounded in internal knowledge, or explicit override.
    if requires_rag is None:
        requires_rag = any(n in text for n in _RAG_NOUNS)
    else:
        requires_rag = bool(requires_rag)

    # Modality
    if has_image_input:
        modality = "image+text" if (requires_vision or requires_rag) else "image"
    else:
        modality = "text"

    # Task type
    if task_type:
        ttype = task_type
    elif requires_vision and requires_rag:
        ttype = TaskType.MULTIMODAL_ANALYSIS.value
    elif requires_vision:
        ttype = TaskType.DOCUMENT_ANALYSIS.value
    elif requires_code:
        ttype = TaskType.CODING.value
    elif requires_rag:
        ttype = TaskType.RAG_QA.value
    else:
        ttype = TaskType.GENERAL_QA.value

    # Tools: code always needs the sandbox; vision may feed RAG/artifact tools.
    if requires_tools is None:
        requires_tools = bool(requires_code)
    else:
        requires_tools = bool(requires_tools)

    # Complexity heuristic
    if complexity:
        comp = complexity
    elif ttype == TaskType.MULTIMODAL_ANALYSIS.value:
        comp = "high"
    elif requires_code and requires_rag:
        comp = "high"
    elif requires_code or requires_rag or requires_vision:
        comp = "medium"
    else:
        comp = "low"

    return {
        "task_type": ttype,
        "modality": modality,
        "has_image": bool(has_image_input),
        "requires_vision": requires_vision,
        "requires_code": requires_code,
        "requires_rag": requires_rag,
        "requires_tools": requires_tools,
        "complexity": comp,
    }


# ---------------------------------------------------------------------------
# Capability -> model selection
# ---------------------------------------------------------------------------
def _select_local_model(capability: str, modality: str) -> Optional[str]:
    """Return the id of the best LOCAL model for ``capability`` (or None)."""
    candidates = get_models_with_capability(capability, modality)
    if not candidates:
        return None
    return candidates[0][0]


def _required_capabilities(chars: Dict) -> List[str]:
    """Ordered list of capabilities a task needs."""
    caps: List[str] = []
    if chars["requires_vision"]:
        caps.append("vision")
    if chars["requires_code"]:
        caps.append("code_generation")
    if chars["requires_rag"] or chars["task_type"] == TaskType.RAG_QA.value:
        caps.append("rag_synthesis")
    # Fallback reasoning/text generation if nothing else selected.
    if not caps:
        caps.append("reasoning")
    return caps


# ---------------------------------------------------------------------------
# Public routing API
# ---------------------------------------------------------------------------
def route(req: RoutingRequest) -> RoutingDecision:
    """Classify and route ``req`` to local model(s); return a RoutingDecision.

    Raises ``NoLocalModelAvailable`` if a required capability cannot be served by
    any local model (never silently routes to an external model).
    """
    t0 = time.time()
    chars = classify_task(
        req.task,
        has_image=req.has_image,
        image_path=req.image_path,
        requires_code=req.requires_code,
        requires_vision=req.requires_vision,
        requires_rag=req.requires_rag,
        requires_tools=req.requires_tools,
        task_type=req.task_type,
        complexity=req.complexity,
    )

    caps = _required_capabilities(chars)

    # Resolve every required capability to a LOCAL model.
    models_required: List[str] = []
    selected_model: Optional[str] = None
    used_caps: List[str] = []
    for cap in caps:
        mid = _select_local_model(cap, chars["modality"])
        if mid is None:
            raise NoLocalModelAvailable(
                f"No LOCAL model provides capability '{capability_label(cap)}'. "
                f"Sovereign AI will not route to an external model."
            )
        # Sovereignty: the selected model's endpoint MUST be local.
        validate_local_endpoint(get_model(mid)["endpoint"])
        if mid not in models_required:
            models_required.append(mid)
        used_caps.append(cap)
        if selected_model is None:
            selected_model = mid

    # Primary model is the one matching the highest-priority capability.
    if chars["requires_vision"]:
        selected_model = "vision"
    elif chars["requires_code"]:
        selected_model = "qwen-coder"
    elif chars["requires_rag"] or chars["task_type"] == TaskType.RAG_QA.value:
        selected_model = "general"
    else:
        selected_model = selected_model or "general"

    # Confidence from the dominant signal.
    if chars["requires_vision"] and chars["requires_rag"]:
        confidence = 0.90
    elif chars["requires_vision"]:
        confidence = 0.92
    elif chars["requires_code"]:
        confidence = 0.88
    elif chars["requires_rag"]:
        confidence = 0.82
    else:
        confidence = 0.70

    # Build an explainable reason.
    reasons = []
    if chars["has_image"]:
        reasons.append("image input detected")
    if chars["requires_vision"]:
        reasons.append("vision / image analysis required")
    if chars["requires_code"]:
        reasons.append("code generation / execution required")
    if chars["requires_rag"]:
        reasons.append("grounded in local knowledge base (RAG)")
    if chars["requires_tools"]:
        reasons.append("local tool / sandbox required")
    reason = "; ".join(reasons) if reasons else "general text task"

    all_local = all(get_model(m).get("local") is True for m in models_required)

    decision = RoutingDecision(
        task_type=chars["task_type"],
        modality=chars["modality"],
        selected_model=selected_model,
        models_required=models_required,
        requires_rag=chars["requires_rag"],
        requires_tools=chars["requires_tools"],
        confidence=confidence,
        reason=reason,
        capabilities=[capability_label(c) for c in used_caps],
        local_only=bool(req.local_only),
        all_local=all_local,
        external_calls=0,
    )
    logger.info(
        "route -> %s | task=%s modality=%s models=%s (%.1fms)",
        selected_model, chars["task_type"], chars["modality"],
        models_required, (time.time() - t0) * 1000,
    )
    return decision


def get_model_capabilities(model_id: str) -> List[str]:
    m = get_model(model_id)
    return m.get("capabilities", []) if m else []


def route_task(task_type: str, has_image: bool = False) -> str:
    """Backward-compatible thin wrapper: return the primary selected model id."""
    decision = route(RoutingRequest(task_type=task_type, has_image=has_image))
    return decision.selected_model


# ---------------------------------------------------------------------------
# Execution (dispatches to the EXISTING model clients / tools — no new server)
# ---------------------------------------------------------------------------
def execute_routing(
    decision: RoutingDecision,
    task: str = "",
    image_path: str = None,
    asset_tag: str = "R-1001",
    prompt: str = None,
    max_tokens: int = 1024,
) -> Dict:
    """Run a routed task using the existing local clients/tools.

    Returns a dict with the per-model outputs, the models actually used, and a
    guarantee that ``external_calls == 0``. Import of the heavy agent tools is
    deferred so routing-only callers never pay the import cost.
    """
    from agent.security.netguard import no_network  # safeguard

    out: Dict = {"models_used": [], "external_calls": 0, "outputs": {}}

    with no_network() as guard:
        # 1) Vision extraction (if required).
        if "vision" in decision.models_required and image_path:
            from agent.tools.vision import analyze_image, extract_equipment_tags

            analysis_type = "pid" if ("pid" in (task or "").lower()) else "general"
            res = analyze_image(image_path, prompt=prompt or task, analysis_type=analysis_type)
            tags = extract_equipment_tags(res)
            out["outputs"]["vision"] = res
            out["outputs"]["vision_tags"] = tags
            out["models_used"].append("vision")

        # 2) Code generation + sandbox (if required).
        if "qwen-coder" in decision.models_required:
            from agent.coder.model import complete
            from agent.tools.python_execute import python_execute

            code_prompt = (
                f"You are a helpful coding assistant. {task}\n"
                "Return ONLY a complete, runnable Python implementation "
                "(no prose, no markdown fences)."
            )
            code = complete(
                [{"role": "user", "content": code_prompt}],
                max_tokens=max_tokens,
            )
            code = _strip_code_fence(code)
            sand = python_execute(code, timeout=30)
            out["outputs"]["code"] = code
            out["outputs"]["sandbox"] = sand
            out["models_used"].append("coder")

        # 3) General reasoning + RAG (if required).
        if "general" in decision.models_required:
            rag_evidence = []
            if decision.requires_rag:
                from agent.tools.search_kb import search_knowledge_base

                hits = search_knowledge_base(
                    task or asset_tag, asset_tag=asset_tag, top_k=6
                )
                rag_evidence = [
                    {"source_file": h.get("source_file"), "document_type": h.get("document_type"),
                     "score": round(float(h.get("score", 0.0)), 3),
                     "text": (h.get("text") or "")[:600]}
                    for h in hits
                ]
            out["outputs"]["rag_evidence"] = rag_evidence
            # Attempt local general synthesis if the server is reachable.
            synth = _try_general_synthesis(decision, task, rag_evidence, max_tokens)
            out["outputs"]["synthesis"] = synth
            out["models_used"].append("general")

        out["external_calls"] = guard.external_calls

    return out


def _strip_code_fence(text: str) -> str:
    if "```" in text:
        m = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
    return text.strip()


def _try_general_synthesis(decision, task, rag_evidence, max_tokens) -> Dict:
    """Call the local general model if reachable; otherwise report RAG-only.

    Never raises — a missing general server must not break the routing demo, it
    is reported transparently (the repo's agent performs reasoning programmatically
    and this path simply mirrors that with retrieved evidence).
    """
    from app.models.registry import get_model, is_local_endpoint
    import httpx

    m = get_model("general")
    endpoint = m["endpoint"] if m else None
    if not endpoint or not is_local_endpoint(endpoint):
        return {"used": False, "reason": "general endpoint not local/configured",
                "rag_evidence_count": len(rag_evidence)}
    try:
        with httpx.Client(timeout=3.0) as c:
            ok = c.get(f"{endpoint}/models").status_code == 200
    except Exception:
        ok = False
    if not ok:
        return {"used": False, "reason": "general model server not running on this host",
                "rag_evidence_count": len(rag_evidence)}
    # Server is up — use the existing client.
    from app.models.client import ModelClient

    ctx = "\n".join(f"- {e['text']}" for e in rag_evidence[:4]) or "(no retrieved evidence)"
    messages = [
        {"role": "system", "content": "You are Sovereign AI. Answer using ONLY the provided local evidence."},
        {"role": "user", "content": f"Task: {task}\n\nLocal evidence:\n{ctx}"},
    ]
    try:
        client = ModelClient("general", endpoint)
        answer = client.generate(messages, max_tokens=max_tokens)
        return {"used": True, "answer": answer}
    except Exception as e:
        return {"used": False, "reason": f"general synthesis failed: {e}",
                "rag_evidence_count": len(rag_evidence)}
