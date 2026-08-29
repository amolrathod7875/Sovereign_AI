"""Batch P&ID analyzer using the local CUDA llama-server (Qwen2.5-VL).

For every image in a folder, asks Qwen-VL for structured P&ID metadata and
writes a consolidated Markdown report (summary table + per-drawing detail).

Usage:
  python analyze_pid.py <image_folder> [output_md]
Defaults: test/ folder -> PID_analysis_report.md
"""
import base64
import io
import json
import os
import re
import sys
import time

from openai import OpenAI
from PIL import Image

SERVER = "http://localhost:8003/v1"
client = OpenAI(base_url=SERVER, api_key="none")

FIELDS = [
    "DRAWING_ID", "PLANT_PROCESS", "MAJOR_EQUIPMENT", "EQUIPMENT_TAGS",
    "PUMPS", "TANKS_VESSELS", "HEAT_EXCHANGERS", "COMPRESSORS",
    "VALVES", "INSTRUMENTS", "PROCESS_FLOW", "UNCERTAIN",
]

PROMPT = (
    "You are a P&ID (Piping & Instrumentation Diagram) analysis engine. "
    "Analyze this drawing and respond with ONLY a JSON object (no markdown fences, "
    "no extra commentary) using exactly these keys:\n"
    '{"DRAWING_ID": "", "PLANT_PROCESS": "", "MAJOR_EQUIPMENT": "", '
    '"EQUIPMENT_TAGS": "", "PUMPS": "", "TANKS_VESSELS": "", "HEAT_EXCHANGERS": "", '
    '"COMPRESSORS": "", "VALVES": "", "INSTRUMENTS": "", "PROCESS_FLOW": "", '
    '"UNCERTAIN": ""}\n'
    "Rules:\n"
    "- Each value is a short comma-separated string or \"N/A\".\n"
    "- NEVER enumerate long auto-incrementing tag sequences. Show at most 5 example "
    "tags per field; summarize the rest (e.g. \"~60 G-* tags, mostly vessels\").\n"
    "- Do not invent tags; if illegible say so in UNCERTAIN.\n"
    "Example of the required concise style:\n"
    '{"DRAWING_ID": "51Y613", "PLANT_PROCESS": "Grit Washer / Grit Classifier", '
    '"MAJOR_EQUIPMENT": "Grit washer, grit classifier", '
    '"EQUIPMENT_TAGS": "GWA-51-371, GCA-51-376", "PUMPS": "P-101", '
    '"TANKS_VESSELS": "N/A", "HEAT_EXCHANGERS": "N/A", "COMPRESSORS": "N/A", '
    '"VALVES": "HV-1, TV-42", "INSTRUMENTS": "LT, TC, LC", '
    '"PROCESS_FLOW": "influent -> grit washer -> grit classifier -> outflow", '
    '"UNCERTAIN": "some tag numbers partially illegible"}'
)

MAX_W = 1280  # downscale long edge to bound latency/accuracy


def prepare(path: str) -> str:
    img = Image.open(path)
    if max(img.size) > MAX_W:
        scale = MAX_W / max(img.size)
        img = img.resize((int(img.size[0] * scale), int(img.size[1] * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def parse(text: str) -> dict:
    out = {f: "N/A" for f in FIELDS}
    raw = text.strip()
    # extract the JSON object span (handles truncated / fenced output)
    s, e = raw.find("{"), raw.rfind("}")
    blob = raw[s:e + 1] if (s != -1 and e != -1 and e > s) else raw
    try:
        data = json.loads(blob)
        for f in FIELDS:
            if f in data and data[f] not in (None, ""):
                out[f] = str(data[f]).strip()
        return out
    except Exception:
        pass
    # fallback: LABEL: value lines
    for f in FIELDS:
        m = re.search(rf"^{re.escape(f)}\s*:\s*(.+)$", raw, re.IGNORECASE | re.MULTILINE)
        if m:
            out[f] = m.group(1).strip()
    return out


def analyze(path: str) -> dict:
    t0 = time.time()
    resp = client.chat.completions.create(
        model="qwen-vl",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{prepare(path)}"}},
                {"type": "text", "text": PROMPT},
            ],
        }],
        max_tokens=512,
        temperature=0.1,
    )
    raw = resp.choices[0].message.content
    rec = parse(raw)
    rec["_elapsed"] = round(time.time() - t0, 1)
    rec["_raw"] = raw
    rec["_file"] = os.path.basename(path)
    return rec


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else r"D:\Sovereign_AI\PID_Dataset\0__raw_data\sheets\test"
    out_md = sys.argv[2] if len(sys.argv) > 2 else r"D:\Sovereign_AI\PID_analysis_report.md"

    exts = (".jpg", ".jpeg", ".png", ".bmp")
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(exts))
    print(f"Found {len(files)} drawings in {folder}")

    results = []
    for f in files:
        print(f"Analyzing {f} ...")
        try:
            results.append(analyze(os.path.join(folder, f)))
        except Exception as e:
            print(f"  ERROR {f}: {e}")
            results.append({"_file": f, "_elapsed": 0, "_raw": f"ERROR: {e}"})

    # ---- Markdown report ----
    lines = ["# P&ID Analysis Report", ""]
    lines.append(f"- **Engine:** local Qwen2.5-VL 3B (Q4_K_M) via CUDA llama-server (RTX 4050 6 GB)")
    lines.append(f"- **Source folder:** `{folder}`")
    lines.append(f"- **Drawings analyzed:** {len(results)}")
    lines.append(f"- **Prompt:** structured 12-field P&ID extraction")
    lines.append("")
    lines.append("## Summary Table")
    lines.append("")
    header = "| Drawing | Plant/Process | Major Equipment | Tags | Pumps | Tanks/Vessels | HX | Compressors | Valves | Instruments | Uncertain | sec |"
    sep = "|---|---|---|---|---|---|---|---|---|---|---|---|"
    lines += [header, sep]
    for r in results:
        row = [r.get("_file", ""), r.get("PLANT_PROCESS", ""), r.get("MAJOR_EQUIPMENT", ""),
               r.get("EQUIPMENT_TAGS", ""), r.get("PUMPS", ""), r.get("TANKS_VESSELS", ""),
               r.get("HEAT_EXCHANGERS", ""), r.get("COMPRESSORS", ""), r.get("VALVES", ""),
               r.get("INSTRUMENTS", ""), r.get("UNCERTAIN", ""), str(r.get("_elapsed", ""))]
        row = [c.replace("\n", " ").replace("|", "/") for c in row]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    lines.append("## Per-Drawing Details")
    lines.append("")
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r.get('_file', '')}  _({r.get('_elapsed', '')} s)_")
        lines.append("")
        for f in FIELDS:
            lines.append(f"- **{f.replace('_', ' ').title()}:** {r.get(f, 'N/A')}")
        lines.append("")
        lines.append("<details><summary>Raw model output</summary>")
        lines.append("")
        lines.append("```")
        lines.append(r.get("_raw", ""))
        lines.append("```")
        lines.append("</details>")
        lines.append("")

    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"Report written to {out_md}")


if __name__ == "__main__":
    main()
