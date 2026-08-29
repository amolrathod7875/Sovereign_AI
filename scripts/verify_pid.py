"""Verification & cleanup pass for the P&ID equipment registry (REVISED).

RAW P&ID -> VERIFIED STRUCTURED REPRESENTATION (local, sovereign).
Reuses CUDA llama-server (Qwen2.5-VL-3B) at http://localhost:8003/v1.

Stage 1 (locate): reliable tag-listing prompt on a fine grid of crops -> for each
         candidate tag, find which crop region(s) it appears in (visually grounded).
Stage 2 (classify): focused crop around the tag's region -> simple class/type question
         anchored to the known tag. Instrument loop prefixes are detected by rule, fixing
         the original bug (PIC/LT/TT/FT/PT were mis-classed as Pump/Tank).

Outputs: verified_equipment_registry.json, instrument_registry.json,
         stream_registry.json, reports/verification_report.md
"""
import base64
import io
import json
import os
import re
import time
from collections import defaultdict

from openai import OpenAI
from PIL import Image

SERVER = "http://localhost:8003/v1"
client = OpenAI(base_url=SERVER, api_key="none")

ROOT = r"D:\Sovereign_AI\data\pid_analysis"
SHEETS = r"D:\Sovereign_AI\PID_Dataset\0__raw_data\sheets\test"
CROP_DIR = os.path.join(ROOT, "verify_crops")
RAW_DIR = os.path.join(ROOT, "raw")
REG_DIR = os.path.join(ROOT, "registry")
os.makedirs(CROP_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

MODEL = "Qwen2.5-VL-3B-Instruct"
DRAWINGS = ["158.jpg", "157.jpg", "176.jpg", "194.jpg", "196.jpg"]

MAX_WHOLE = 1280
OVERLAP = 100
GRID_COLS = 4
GRID_ROWS = 2

# ---- Stage 1: reliable tag-listing prompt (proven to work on this 3B model) ----
STAGE1_PROMPT = (
    "This is a cropped region of a P&ID. List every visible TAG exactly as written. "
    "Return ONLY JSON (no markdown):\n"
    '{"tags":[""], "instruments":[""], "notes":""}\n'
    "Include equipment tags (P-1001, R-1001, V-1001, E-1005, C-1001, VBF-55-423, GWA-51-371) "
    "and instrument/loop tags (PIC-101, LT-101, PT-100, TT-1001, FT-100, PCV-200). "
    "Preserve EXACT text; use '?' for unreadable characters. Do not invent. If none, return empty arrays."
)

# ---- Stage 2: simple classification on a focused crop, anchored to the known tag ----
def focus_prompt(tag):
    return (
        f"Look at this cropped region of a P&ID. The tagged item we are verifying is '{tag}'.\n"
        "Examine the symbol/diagram next to that tag.\n"
        "Return ONLY JSON (no markdown):\n"
        '{"class":"","equipment_type":"","instrument_type":""}\n'
        "class must be exactly one of: equipment, instrument, valve, stream, annotation, unknown.\n"
        "equipment_type (if equipment): Pump, Reactor, Heat Exchanger, Compressor, Tank, Heater, "
        "Vessel, Filter, Valve, Other.\n"
        "instrument_type (if instrument): e.g. Pressure Indicating Controller, Level Transmitter, "
        "Temperature Transmitter, Flow Transmitter.\n"
        "If you cannot determine the class from the symbol, use unknown. Do not invent."
    )

WHOLE_PROMPT = (
    "Verify this P&ID. Return ONLY JSON (no markdown):\n"
    '{"plant_or_system":"","streams":[{"description":"","from":"","to":""}],"notes":""}\n'
    "plant_or_system: the plant/process name shown in the drawing title block, or UNKNOWN.\n"
    "streams: any visible process-stream TEXT labels (fluid/flow descriptions). For each give "
    "description and from/to if shown.\n"
    "Do NOT invent. Use UNKNOWN if not shown."
)

INSTR_PREFIXES = (
    "PIC", "PIT", "LIT", "TIT", "FIT", "PY", "LT", "PT", "TT", "FT", "LS", "PS", "TS", "FS",
    "PAH", "PAL", "LAH", "LAL", "TAH", "TAL", "FAH", "FAL", "PCV", "LCV", "TCV", "FCV",
    "TCU", "PI", "TI", "LI", "FI", "PA", "LA", "TA", "FA", "PIR", "LIR", "TIR", "FIR",
)
VALVE_PREFIXES = ("HV", "XV", "PV", "MV", "UV", "CV", "SV", "ZS", "ZV", "BD", "SD", "AV")
TAG_RE = re.compile(r"\b[A-Z]{1,4}[/-]?\d[\w\-?]*\b")


def is_instrument_tag(tag):
    t = tag.upper().strip()
    for p in INSTR_PREFIXES:
        if t == p or t.startswith(p + "-") or t.startswith(p + "/") or t.startswith(p + " "):
            return True
    return False


def is_valve_tag(tag):
    t = tag.upper().strip()
    for p in VALVE_PREFIXES:
        if t.startswith(p + "-") or t == p:
            return True
    return False


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9_\-]", "_", str(s))


def base_tag(tag):
    t = tag.upper().strip()
    t = re.sub(r"/[ABC](/?[ABC])*$", "", t)
    t = re.sub(r"([A-Z0-9\-]+)[ABC]$", r"\1", t)
    return t


def b64(img):
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def extract_json(text):
    raw = text.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.I).strip()
    raw = re.sub(r"```$", "", raw).strip()
    for a, b in (("[", "]"), ("{", "}")):
        s, e = raw.find(a), raw.rfind(b)
        if s != -1 and e != -1 and e > s:
            try:
                val = json.loads(raw[s:e + 1])
                if isinstance(val, list):
                    val = next((x for x in val if isinstance(x, dict)), {})
                return val, raw
            except Exception:
                pass
    return None, raw


def analyze(img_b64, prompt, max_tokens):
    resp = client.chat.completions.create(
        model="qwen-vl",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            {"type": "text", "text": prompt},
        ]}],
        max_tokens=max_tokens, temperature=0.1,
    )
    return resp.choices[0].message.content


def make_grid(path):
    img = Image.open(path)
    w, h = img.size
    crops = []
    sx, sy = w / GRID_COLS, h / GRID_ROWS
    idx = 0
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            x0 = max(0, int(c * sx - OVERLAP))
            x1 = min(w, int((c + 1) * sx + OVERLAP))
            y0 = max(0, int(r * sy - OVERLAP))
            y1 = min(h, int((r + 1) * sy + OVERLAP))
            crops.append((idx, img.crop((x0, y0, x1, y1)),
                          {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}))
            idx += 1
    return img, w, h, crops


def harvest_prior_tags(did):
    """Harvest tags from the EARLIER verified pass raw texts (reliable tag-listing)
    to improve recall of candidate locations. Returns a set of tag strings."""
    import glob
    tags = set()
    for pat in (os.path.join(RAW_DIR, f"{did}_crop*.txt"),
                os.path.join(RAW_DIR, f"{did}_whole.txt")):
        for fp in glob.glob(pat):
            try:
                txt = open(fp, encoding="utf-8").read()
            except Exception:
                continue
            obj, _ = extract_json(txt)
            if isinstance(obj, dict):
                for k in ("tags", "instruments"):
                    for t in (obj.get(k) or []):
                        if t:
                            tags.add(str(t).strip())
            for t in TAG_RE.findall(txt):
                tags.add(t.strip())
    return tags


def main():
    with open(os.path.join(REG_DIR, "equipment_registry.json"), encoding="utf-8") as f:
        old = json.load(f)

    candidates = {}
    for item in old["equipment"]:
        tag = item["tag"]
        b = base_tag(tag)
        rec = candidates.setdefault(b, {
            "base": b, "variants": [], "old_type": item["equipment_type"],
            "old_system": item["system"], "source_drawing": item["source_drawing"],
        })
        if tag not in rec["variants"]:
            rec["variants"].append(tag)

    per_drawing = {}
    for fname in DRAWINGS:
        path = os.path.join(SHEETS, fname)
        did = os.path.splitext(fname)[0]
        img, w, h, crops = make_grid(path)

        wimg = img.copy()
        if max(wimg.size) > MAX_WHOLE:
            sc = MAX_WHOLE / max(wimg.size)
            wimg = wimg.resize((int(wimg.size[0] * sc), int(wimg.size[1] * sc)), Image.LANCZOS)
        whole_text = analyze(b64(wimg), WHOLE_PROMPT, 400)
        whole, _ = extract_json(whole_text)
        if whole is None:
            whole = {}
        with open(os.path.join(RAW_DIR, f"verify_{did}_whole.txt"), "w", encoding="utf-8") as f:
            f.write(whole_text)

        extracted = []  # {tag, crop_idx, region}
        for idx, crop, meta in crops:
            cpath = os.path.join(CROP_DIR, f"{did}_c{idx}.jpg")
            crop.save(cpath, "JPEG", quality=90)
            ctext = analyze(b64(crop), STAGE1_PROMPT, 350)
            with open(os.path.join(RAW_DIR, f"verify_{did}_crop{idx}.txt"), "w", encoding="utf-8") as f:
                f.write(ctext)
            obj, _ = extract_json(ctext)
            tags = set()
            if isinstance(obj, dict):
                for k in ("tags", "instruments"):
                    for t in (obj.get(k) or []):
                        if t:
                            tags.add(str(t).strip())
            # regex fallback from raw text
            for t in TAG_RE.findall(ctext):
                tags.add(t.strip())
            for t in tags:
                if t:
                    extracted.append({"tag": t, "crop_idx": idx, "region": dict(meta)})
        prior_tags = harvest_prior_tags(did)
        per_drawing[did] = {
            "plant_or_system": whole.get("plant_or_system") or "UNKNOWN",
            "whole_streams": whole.get("streams") or [],
            "notes": whole.get("notes") or "",
            "extracted": extracted, "prior_tags": prior_tags, "dims": [w, h],
        }
        print(f"[stage1] {fname} plant={per_drawing[did]['plant_or_system']} "
              f"tags_found={len(extracted)} unique={len(set(e['tag'] for e in extracted))}")

    extracted_index = defaultdict(list)
    for did, d in per_drawing.items():
        for occ in d["extracted"]:
            extracted_index[base_tag(occ["tag"])].append({**occ, "drawing": did})

    # prior-text index (earlier verified pass) for recall of candidate locations
    prior_index = defaultdict(list)
    for did, d in per_drawing.items():
        W, H = d["dims"]
        for t in d.get("prior_tags", []):
            prior_index[base_tag(t)].append({"tag": t, "drawing": did,
                                             "region": {"x": 0, "y": 0, "width": W, "height": H}})

    def instr_type_from_tag(tag):
        t = tag.upper()
        if t.startswith("PIC") or t.startswith("PIT") or t.startswith("PI"):
            return "Pressure Indicating Controller"
        if t.startswith("LIT") or t.startswith("LI") or t.startswith("LT"):
            return "Level Transmitter"
        if t.startswith("TIT") or t.startswith("TI") or t.startswith("TT"):
            return "Temperature Transmitter"
        if t.startswith("FIT") or t.startswith("FI") or t.startswith("FT"):
            return "Flow Transmitter"
        if t.startswith("PCV"):
            return "Pressure Control Valve"
        if t.startswith("LCV"):
            return "Level Control Valve"
        if t.startswith("TCV"):
            return "Temperature Control Valve"
        if t.startswith("FCV"):
            return "Flow Control Valve"
        return "Instrument"

    def classify_item(tag):
        """Classify from the ISA-style tag prefix (visually present on the drawing).
        Vision is used only to resolve instrument-loop and V vessel/valve ambiguity."""
        t = tag.upper()
        if is_instrument_tag(t):
            return ("instrument", instr_type_from_tag(tag))
        if is_valve_tag(t):
            return ("valve", "Valve")
        if t.startswith("GWA"):
            return ("equipment", "Grit Washer")
        if t.startswith("GCA"):
            return ("equipment", "Grit Classifier")
        if t.startswith("VBF"):
            return ("equipment", "Filter")
        m = re.match(r"([A-Z]+)", t)
        lead = m.group(1) if m else ""
        if lead == "P":
            return ("equipment", "Pump")
        if lead == "R":
            return ("equipment", "Reactor")
        if lead == "E":
            return ("equipment", "Heat Exchanger")
        if lead == "C":
            return ("equipment", "Compressor")
        if lead == "H":
            return ("equipment", "Heater")
        if lead == "T":
            return ("equipment", "Tank")
        if lead == "V":
            return ("equipment", "Vessel/Valve")
        return ("equipment", "Other")

    def tightest_region(occs):
        best, ba = None, None
        for o in occs:
            r = o["region"]; a = r["width"] * r["height"]
            if ba is None or a < ba:
                best, ba = r, a
        return best

    STREAM_KW = re.compile(
        r"\b(FROM|TO|UNDERFLOW|SHEET|SOLUTION|SLURRY|FLOW|STREAM|CLARIFIER|CIRCULATION|PRODUCT)\b",
        re.I)

    equipment, instruments, streams, unverified = [], [], [], []

    for b, cand in candidates.items():
        did = cand["source_drawing"].replace(".jpg", "")
        plant = per_drawing.get(did, {}).get("plant_or_system", "UNKNOWN")
        tag0 = cand["variants"][0]

        # process-stream description text (not a tag) -> stream registry
        if " " in tag0 and len(tag0) > 12 and STREAM_KW.search(tag0):
            streams.append({"description": tag0, "source_drawing": cand["source_drawing"],
                            "from": "", "to": "", "confidence": 0.7})
            continue

        fresh = extracted_index.get(b)
        prior = prior_index.get(b)
        if not fresh and not prior:
            unverified.append({
                "tag": tag0, "variants": cand["variants"],
                "old_type": cand["old_type"], "old_system": cand["old_system"],
                "source_drawing": cand["source_drawing"],
                "reason": "Tag not located in verification crops nor in prior extraction.",
            })
            continue

        if fresh:
            occs = fresh
            region = tightest_region(occs)
            n_fresh = len(occs)
        else:
            occs = prior
            region = occs[0]["region"]
            n_fresh = 0

        img = Image.open(os.path.join(SHEETS, did + ".jpg"))
        W, H = img.size
        fx0 = max(0, int(region["x"])); fy0 = max(0, int(region["y"]))
        fx1 = min(W, int(region["x"] + region["width"])); fy1 = min(H, int(region["y"] + region["height"]))
        pad = 40
        fx0 = max(0, fx0 - pad); fy0 = max(0, fy0 - pad)
        fx1 = min(W, fx1 + pad); fy1 = min(H, fy1 + pad)
        fcrop = img.crop((fx0, fy0, fx1, fy1))
        fpath = os.path.join(CROP_DIR, f"focus_{did}_{safe_name(b)}.jpg")
        fcrop.save(fpath, "JPEG", quality=90)
        best_tag = max(occs, key=lambda o: len(o["tag"]))["tag"]
        ftext = analyze(b64(fcrop), focus_prompt(best_tag), 200)
        fo, _ = extract_json(ftext)
        if fo is None:
            fo = {}
        with open(os.path.join(RAW_DIR, f"vfoc_{did}_{safe_name(b)}.txt"), "w", encoding="utf-8") as f:
            f.write(ftext)
        fr_class = (fo.get("class") or "unknown").lower()

        cls, eq_type = classify_item(best_tag)

        # resolve V vessel/valve ambiguity using vision
        if eq_type == "Vessel/Valve":
            if fr_class == "valve":
                eq_type = "Valve"
            elif fr_class == "equipment" and (fo.get("equipment_type") or "").lower() == "vessel":
                eq_type = "Vessel"
            else:
                eq_type = "Vessel/Valve"

        if cls == "instrument":
            conf = 0.9 if n_fresh >= 2 else (0.8 if n_fresh == 1 else 0.6)
            status = "verified" if n_fresh >= 2 else ("probable" if n_fresh == 1 else "uncertain")
            instruments.append({"tag": best_tag, "instrument_type": instr_type_from_tag(best_tag),
                                "source_drawing": cand["source_drawing"],
                                "confidence": conf, "verification_status": status})
        elif cls == "valve":
            conf = 0.9 if n_fresh >= 2 else (0.8 if n_fresh == 1 else 0.6)
            status = "verified" if n_fresh >= 2 else ("probable" if n_fresh == 1 else "uncertain")
            equipment.append({"tag": best_tag, "equipment_type": "Valve", "system": plant,
                              "source_drawing": cand["source_drawing"], "location": region,
                              "confidence": conf, "verification_status": status})
        else:  # equipment
            if eq_type == "Vessel/Valve":
                status, conf = "uncertain", 0.5
            else:
                status = "verified" if n_fresh >= 2 else ("probable" if n_fresh == 1 else "uncertain")
                conf = 0.9 if n_fresh >= 2 else (0.8 if n_fresh == 1 else 0.6)
            equipment.append({"tag": best_tag, "equipment_type": eq_type, "system": plant,
                              "source_drawing": cand["source_drawing"], "location": region,
                              "confidence": conf, "verification_status": status})

    for did, d in per_drawing.items():
        for s in d["whole_streams"]:
            desc = (s.get("description") or "").strip()
            if desc:
                streams.append({"description": desc, "source_drawing": did + ".jpg",
                                "from": s.get("from") or "", "to": s.get("to") or "",
                                "confidence": 0.7})
    seen = set(); ded = []
    for s in streams:
        k = (s["description"].lower(), s["source_drawing"])
        if k not in seen:
            seen.add(k); ded.append(s)
    streams = ded

    with open(os.path.join(REG_DIR, "verified_equipment_registry.json"), "w", encoding="utf-8") as f:
        json.dump(equipment, f, indent=2, ensure_ascii=False)
    with open(os.path.join(REG_DIR, "instrument_registry.json"), "w", encoding="utf-8") as f:
        json.dump(instruments, f, indent=2, ensure_ascii=False)
    with open(os.path.join(REG_DIR, "stream_registry.json"), "w", encoding="utf-8") as f:
        json.dump(streams, f, indent=2, ensure_ascii=False)
    with open(os.path.join(ROOT, "verify_intermediate.json"), "w", encoding="utf-8") as f:
        json.dump({"equipment": equipment, "instruments": instruments, "streams": streams,
                   "unverified": unverified,
                   "plants": {d: per_drawing[d]["plant_or_system"] for d in per_drawing}},
                  f, indent=2, ensure_ascii=False)

    print(f"Equipment={len(equipment)} Instruments={len(instruments)} "
          f"Streams={len(streams)} Unverified={len(unverified)}")


if __name__ == "__main__":
    main()
