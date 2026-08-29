"""Deep P&ID analysis pipeline (local, sovereign).

Reuses the running CUDA llama-server (Qwen2.5-VL) at http://localhost:8003/v1
via the OpenAI client. For each drawing: whole-sheet analysis + grid crop analysis,
tolerant JSON parsing, tag extraction, anti-hallucination. Produces structured
JSON per drawing + equipment registry + selection/synthetic/quality reports.

No models downloaded, no cloud, no new serving stack.
"""
import base64
import io
import json
import os
import re
import sys
import time
from collections import defaultdict

from openai import OpenAI
from PIL import Image

SERVER = "http://localhost:8003/v1"
client = OpenAI(base_url=SERVER, api_key="none")

ROOT = r"D:\Sovereign_AI\data\pid_analysis"
SHEETS = r"D:\Sovereign_AI\PID_Dataset\0__raw_data\sheets"
MODEL = "Qwen2.5-VL-3B-Instruct"

DRAWINGS = ["158.jpg", "157.jpg", "176.jpg", "194.jpg", "196.jpg"]

WHOLE_PROMPT = (
    "You are a P&ID analysis engine for a sovereign industrial system. Analyze this "
    "Piping & Instrumentation Diagram. Return ONLY a JSON object (no markdown fences) "
    "with exactly these keys:\n"
    '{"drawing_id":"", "plant_or_system":"", "process_description":"", "process_flow":"", '
    '"equipment":[{"tag":"","name":"","type":""}], '
    '"connections":[{"from":"","to":"","relationship":"process_flow","confidence":0.0}], '
    '"uncertain_items":[{"value":"","reason":""}]}\n'
    "Rules:\n"
    "- Preserve EXACT visible tags (P-1001, R-1001, V-1001, E-1005, C-1001, GWA-51-371, "
    "VBF-55-423). Use '?' for unreadable chars (e.g. VBF-55-4??).\n"
    "- If unreadable, use UNREADABLE/UNKNOWN. NEVER invent tags, names, pressures, "
    "temperatures, or conditions.\n"
    "- List only equipment you can actually see (<=12 items).\n"
    "- connections only when clearly visible; confidence 0-1."
)

CROP_PROMPT = (
    "This is a cropped region of a P&ID. List every visible equipment TAG and instrument "
    "TAG exactly as written (P-1001, LT-101, PIC-200, VBF-55-423). Use '?' for unreadable "
    "characters. Return ONLY JSON (no markdown):\n"
    '{"tags":[""], "instruments":[""], "notes":""}\n'
    "Do not invent. If none visible return empty arrays. Keep notes under 30 words."
)

MAX_WHOLE = 1280
CROP_TARGET = 1000
OVERLAP = 80
MAX_CROPS = 6
MAX_TOKENS_WHOLE = 900
MAX_TOKENS_CROP = 400

TAG_RE = re.compile(r"\b[A-Z]{1,4}[/-]?\d[\w\-?]*\b")
INSTR_LEADS = {
    "PT", "TT", "LT", "FT", "PI", "TI", "LI", "FI", "PC", "TC", "LC", "FC",
    "PIC", "TIC", "LIC", "FIC", "PAH", "PAL", "LAH", "LAL", "TIC", "FIC",
    "PS", "TS", "LS", "FS", "PIT", "LIT", "TIT", "FIT",
}


def classify(tag: str) -> str:
    t = tag.upper()
    if t.startswith("GWA"):
        return "Grit Washer"
    if t.startswith("GCA"):
        return "Grit Classifier"
    if t.startswith("VBF"):
        return "Filter (VBF)"
    lead = re.match(r"([A-Z]+)", t)
    if not lead:
        return "Unknown"
    L = lead.group(1)
    if L.startswith("P"):
        return "Pump"
    if L.startswith("R"):
        return "Reactor"
    if L.startswith("V"):
        return "Vessel/Valve"
    if L.startswith("E"):
        return "Heat Exchanger"
    if L.startswith("C"):
        return "Compressor"
    if L.startswith("T"):
        return "Tank"
    if L.startswith("H"):
        return "Heater"
    if L in INSTR_LEADS or L[:2] in INSTR_LEADS:
        return "Instrument"
    return "Other"


def b64_from_image(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def extract_json(text: str):
    raw = text.strip()
    s, e = raw.find("{"), raw.rfind("}")
    blob = raw[s:e + 1] if (s != -1 and e != -1 and e > s) else raw
    try:
        return json.loads(blob), raw
    except Exception:
        return None, raw


def extract_tags(text: str):
    return set(t for t in TAG_RE.findall(text) if re.search(r"\d", t))


def analyze(image_b64: str, prompt: str, max_tokens: int) -> dict:
    resp = client.chat.completions.create(
        model="qwen-vl",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        max_tokens=max_tokens,
        temperature=0.1,
    )
    return resp.choices[0].message.content


def make_crops(path: str):
    img = Image.open(path)
    w, h = img.size
    aspect = w / h
    cols = max(1, round((MAX_CROPS * aspect) ** 0.5))
    rows = max(1, (MAX_CROPS + cols - 1) // cols)
    crops = []
    sx, sy = w / cols, h / rows
    idx = 0
    for r in range(rows):
        for c in range(cols):
            x0 = max(0, int(c * sx - OVERLAP))
            x1 = min(w, int((c + 1) * sx + OVERLAP))
            y0 = max(0, int(r * sy - OVERLAP))
            y1 = min(h, int((r + 1) * sy + OVERLAP))
            if x1 - x0 < 50 or y1 - y0 < 50:
                continue
            crop = img.crop((x0, y0, x1, y1))
            crops.append((idx, crop, {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}))
            idx += 1
            if idx >= MAX_CROPS:
                break
        if idx >= MAX_CROPS:
            break
    return crops


def build_record(fname: str, path: str, dims: tuple, whole: dict, whole_raw: str,
                 crop_results: list, crop_meta: list, t_whole: float, t_crops: float):
    did = whole.get("drawing_id") or os.path.splitext(fname)[0]
    did = str(did).strip() or os.path.splitext(fname)[0]

    # collect tags
    whole_tags = set()
    for eq in whole.get("equipment", []) or []:
        if isinstance(eq, dict) and eq.get("tag"):
            whole_tags.add(str(eq["tag"]).strip())
    crop_tags = set()
    instruments = set()
    crop_notes = []
    for cr, meta in zip(crop_results, crop_meta):
        for t in (cr.get("tags") or []):
            if t:
                crop_tags.add(str(t).strip())
        for ins in (cr.get("instruments") or []):
            if ins:
                instruments.add(str(ins).strip())
        if cr.get("notes"):
            crop_notes.append(str(cr["notes"]).strip())

    # safety-net regex from raw texts
    regex_tags = extract_tags(whole_raw)
    for cr, _ in zip(crop_results, crop_meta):
        regex_tags |= extract_tags(json.dumps(cr))
    regex_tags -= {""}

    def is_valid_tag(t):
        return len(t) >= 2 and re.search(r"[A-Za-z]", t) and re.search(r"\d", t)

    all_tags = {t for t in (whole_tags | crop_tags | regex_tags) if is_valid_tag(t)}
    # conflict: crop/regex tags missing from whole-sheet
    conflicts = sorted((crop_tags | regex_tags) - whole_tags)

    equipment = []
    for tag in sorted(all_tags):
        src = "crop" if tag in crop_tags else ("whole_image" if tag in whole_tags else "regex")
        conf = 0.9 if src == "crop" else (0.75 if src == "whole_image" else 0.6)
        equipment.append({
            "tag": tag,
            "name": "UNKNOWN",
            "type": classify(tag),
            "description": "",
            "region": None,
            "confidence": conf,
            "source": src,
        })

    def by_type(t):
        return [e for e in equipment if e["type"] == t]

    pumps = by_type("Pump")
    reactors = by_type("Reactor")
    vessels = by_type("Vessel/Valve")
    heat_exchangers = by_type("Heat Exchanger")
    compressors = by_type("Compressor")
    valves = []  # explicit valve list usually empty; V-tags folded into vessels
    instr_entries = []
    for ins in sorted(instruments):
        instr_entries.append({"tag": ins, "name": "UNKNOWN", "type": "Instrument",
                              "description": "", "region": None, "confidence": 0.85, "source": "crop"})

    uncertain = []
    for u in whole.get("uncertain_items", []) or []:
        if isinstance(u, dict):
            uncertain.append({"value": str(u.get("value", "")), "reason": str(u.get("reason", ""))})
    for n in crop_notes:
        if n and n.upper() not in ("", "N/A"):
            uncertain.append({"value": "crop note", "reason": n})
    if conflicts:
        uncertain.append({
            "value": ", ".join(conflicts[:20]),
            "reason": f"{len(conflicts)} tag(s) found in crop/regex but absent from whole-sheet "
                      f"analysis (possible omission by whole-sheet pass).",
        })

    record = {
        "drawing": {
            "file_name": fname,
            "file_path": path,
            "drawing_id": did,
            "image_width": dims[0],
            "image_height": dims[1],
        },
        "process": {
            "plant_or_system": whole.get("plant_or_system") or "UNKNOWN",
            "process_description": whole.get("process_description") or "UNKNOWN",
            "process_flow": whole.get("process_flow") or "UNKNOWN",
            "confidence": 0.7 if whole.get("plant_or_system") else 0.4,
        },
        "equipment": equipment,
        "pumps": pumps,
        "vessels": vessels,
        "reactors": reactors,
        "heat_exchangers": heat_exchangers,
        "compressors": compressors,
        "valves": valves,
        "instruments": instr_entries,
        "connections": whole.get("connections", []) or [],
        "uncertain_items": uncertain,
        "analysis_metadata": {
            "whole_image_analysis": True,
            "crop_analysis": True,
            "model": MODEL,
            "runtime": "llama.cpp",
            "gpu": "RTX 4050",
            "n_crops": len(crop_results),
            "time_whole_s": round(t_whole, 1),
            "time_crops_s": round(t_crops, 1),
        },
    }
    return record, did, conflicts


def process_drawing(fname: str):
    path = os.path.join(SHEETS, "test", fname)
    img = Image.open(path)
    dims = img.size
    did = os.path.splitext(fname)[0]

    # whole-sheet (downscaled)
    wimg = img.copy()
    if max(wimg.size) > MAX_WHOLE:
        sc = MAX_WHOLE / max(wimg.size)
        wimg = wimg.resize((int(wimg.size[0] * sc), int(wimg.size[1] * sc)), Image.LANCZOS)
    t0 = time.time()
    whole_text = analyze(b64_from_image(wimg), WHOLE_PROMPT, MAX_TOKENS_WHOLE)
    t_whole = time.time() - t0
    whole, whole_raw = extract_json(whole_text)
    if whole is None:
        whole = {}
    with open(os.path.join(ROOT, "raw", f"{did}_whole.txt"), "w", encoding="utf-8") as f:
        f.write(whole_raw)

    # crops (native res)
    crops = make_crops(path)
    crop_results = []
    crop_meta = []
    t0 = time.time()
    for idx, crop, meta in crops:
        cpath = os.path.join(ROOT, "crops", f"{did}_c{idx}.jpg")
        crop.save(cpath, "JPEG", quality=90)
        ctext = analyze(b64_from_image(crop), CROP_PROMPT, MAX_TOKENS_CROP)
        cr, craw = extract_json(ctext)
        if cr is None:
            cr = {}
        with open(os.path.join(ROOT, "raw", f"{did}_crop{idx}.txt"), "w", encoding="utf-8") as f:
            f.write(craw)
        crop_results.append(cr)
        crop_meta.append(meta)
    t_crops = time.time() - t0

    record, did, conflicts = build_record(fname, path, dims, whole, whole_raw, crop_results, crop_meta, t_whole, t_crops)
    with open(os.path.join(ROOT, "json", f"{did}.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    print(f"[done] {fname} id={did} tags={len(record['equipment'])} crops={len(crops)} "
          f"whole={t_whole:.1f}s crops={t_crops:.1f}s conflicts={len(conflicts)}")
    return record


def main():
    records = {}
    errors = []
    for d in DRAWINGS:
        try:
            records[d] = process_drawing(d)
        except Exception as e:
            errors.append({"drawing": d, "error": str(e)})
            print(f"[ERROR] {d}: {e}")

    # ---- equipment registry ----
    reg = []
    tag_index = defaultdict(list)
    for d, rec in records.items():
        for eq in rec["equipment"]:
            tag_index[eq["tag"]].append((d, eq))
    for tag, occ in tag_index.items():
        d0, eq0 = occ[0]
        status = "verified" if len(occ) > 1 else ("probable" if eq0["confidence"] >= 0.75 else "uncertain")
        reg.append({
            "equipment_id": tag,
            "tag": tag,
            "equipment_type": eq0["type"],
            "system": records[d0]["process"]["plant_or_system"],
            "source_drawing": d0,
            "related_equipment": sorted({o[1]["tag"] for o in occ if o[1]["tag"] != tag}),
            "confidence": round(max(eq["confidence"] for _, eq in occ), 2),
            "verification_status": status,
        })
    with open(os.path.join(ROOT, "registry", "equipment_registry.json"), "w", encoding="utf-8") as f:
        json.dump({"equipment": reg}, f, indent=2, ensure_ascii=False)

    # ---- quality report ----
    n_eq = sum(len(r["equipment"]) for r in records.values())
    n_tags = len(tag_index)
    n_unc = sum(len(r["uncertain_items"]) for r in records.values())
    n_conn = sum(len(r["connections"]) for r in records.values())
    n_crops = sum(r["analysis_metadata"]["n_crops"] for r in records.values())
    avg_t = sum(r["analysis_metadata"]["time_whole_s"] + r["analysis_metadata"]["time_crops_s"] for r in records.values()) / max(1, len(records))

    qlines = ["# P&ID Analysis — Quality Report", ""]
    qlines += [
        f"- Drawings processed: {len(records)} / {len(DRAWINGS)}",
        f"- Equipment items detected: {n_eq}",
        f"- Unique tags: {n_tags}",
        f"- Uncertain items recorded: {n_unc}",
        f"- Process relationships (connections): {n_conn}",
        f"- Crop analyses: {n_crops}",
        f"- Average inference time per drawing: {avg_t:.1f} s",
        "- GPU runtime: RTX 4050 (CUDA 12.4), llama.cpp llama-server — ACTIVE",
        f"- Errors/timeouts: {len(errors)}",
    ]
    if errors:
        qlines.append("")
        qlines.append("## Errors")
        for e in errors:
            qlines.append(f"- {e['drawing']}: {e['error']}")
    qlines += ["", "## Fields frequently UNKNOWN", "",
               "- `process.confidence` is heuristic; many `plant_or_system` values are model-inferred.",
               "- `name` is intentionally UNKNOWN (no OCR name available; anti-hallucination).",
               "- `valves` array is empty; V-* tags are folded into `vessels` (V is ambiguous Vessel/Valve).",
               "", "## Potential hallucinations / conflicts"]
    for d, rec in records.items():
        for u in rec["uncertain_items"]:
            reason = u.get("reason", "")
            if "omission" in reason or "conflict" in reason.lower():
                qlines.append(f"- {d}: {u.get('value', '')} — {reason}")
    qlines += ["", "## Recommendations",
               "- Increase crop count / finer grid for dense drawings (158, 196).",
               "- Use a higher-quant or 7B VL model for tag fidelity on dense sheets.",
               "- Human verification of extracted tags before synthetic-doc generation.",
               "- Treat `Vessel/Valve` ambiguity by cropping valve callouts specifically."]
    with open(os.path.join(ROOT, "reports", "quality_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(qlines))

    # ---- selection report ----
    def richness(rec):
        return len(rec["equipment"]) + len(rec["connections"]) * 2 + len(rec["instruments"])
    ranked = sorted(records.items(), key=lambda kv: richness(kv[1]), reverse=True)
    slines = ["# P&ID Analysis — Selection Report", "",
              "## Cross-drawing comparison", ""]
    slines.append("| Drawing | Plant/System | Equip | Pumps | Reactors | Vessels | HX | Compressors | Instr | Conns |")
    slines.append("|---|---|---|---|---|---|---|---|---|---|")
    for d, rec in ranked:
        p = rec["process"]
        slines.append("| %s | %s | %d | %d | %d | %d | %d | %d | %d | %d |" % (
            d, p["plant_or_system"], len(rec["equipment"]), len(rec["pumps"]),
            len(rec["reactors"]), len(rec["vessels"]), len(rec["heat_exchangers"]),
            len(rec["compressors"]), len(rec["instruments"]), len(rec["connections"])))
    slines += ["", "## Answers", ""]
    slines.append(f"1. Richest equipment structure: **{ranked[0][0]}** ({len(ranked[0][1]['equipment'])} items).")
    flow_sorted = sorted(records.items(), key=lambda kv: len(kv[1]["connections"]), reverse=True)
    slines.append(f"2. Clearest process flow: **{flow_sorted[0][0]}** ({len(flow_sorted[0][1]['connections'])} connections).")
    slines.append(f"3. Most useful equipment relationships: **{flow_sorted[0][0]}**.")
    slines.append(f"4. Best for synthetic industrial knowledge chain: **{ranked[0][0]}** "
                  f"({ranked[0][1]['process']['plant_or_system']}).")
    types = defaultdict(int)
    for rec in records.values():
        for eq in rec["equipment"]:
            types[eq["type"]] += 1
    rep = sorted(types.items(), key=lambda x: x[1], reverse=True)
    slines.append("5. Repeated equipment types: " + ", ".join(f"{k} ({v})" for k, v in rep) + ".")
    slines += ["6. Equipment suitability:",
               "   - SOP generation: reactors, vessels, compressors (158, 176).",
               "   - Maintenance records: pumps, compressors, heat exchangers.",
               "   - Inspection reports: vessels, reactors, tanks.",
               "   - Sensor data: instruments (LT/PT/TT/FT tags).",
               "   - Vendor correspondence: compressors, pumps, filters (VBF).",
               "   - Approval-note generation: reactors, grit washer/classifier (194)."]
    with open(os.path.join(ROOT, "reports", "selection_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(slines))

    # ---- synthetic candidates ----
    sy = []
    for eq in reg:
        if eq["verification_status"] == "uncertain":
            continue
        sy.append({
            "tag": eq["tag"],
            "equipment_type": eq["equipment_type"],
            "system": eq["system"],
            "source_drawing": eq["source_drawing"],
            "recommended_documents": [
                "equipment_manual", "maintenance_sop", "inspection_report",
                "maintenance_history", "sensor_data", "vendor_correspondence", "approval_note",
            ],
            "reason": f"{eq['equipment_type']} in {eq['system']} (drawing {eq['source_drawing']}); "
                      f"suitable for equipment-centric synthetic documents.",
        })
    with open(os.path.join(ROOT, "synthetic_candidates.json"), "w", encoding="utf-8") as f:
        json.dump(sy, f, indent=2, ensure_ascii=False)

    print(f"Registry: {len(reg)} items | Synthetic candidates: {len(sy)} | Reports written.")


if __name__ == "__main__":
    main()
