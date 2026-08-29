"""Generate verification_report.md from the verified registries (no model calls)."""
import json
import os
from collections import defaultdict, Counter

ROOT = r"D:\Sovereign_AI\data\pid_analysis"
REG = os.path.join(ROOT, "registry")

equipment = json.load(open(os.path.join(REG, "verified_equipment_registry.json"), encoding="utf-8"))
instruments = json.load(open(os.path.join(REG, "instrument_registry.json"), encoding="utf-8"))
streams = json.load(open(os.path.join(REG, "stream_registry.json"), encoding="utf-8"))

DRAW = ["158.jpg", "157.jpg", "176.jpg", "194.jpg", "196.jpg"]

# ---- stats ----
def by_drawing(items):
    d = defaultdict(list)
    for it in items:
        d[it["source_drawing"]].append(it)
    return d

eq_d = by_drawing(equipment)
in_d = by_drawing(instruments)
st_d = by_drawing(streams)

total = len(equipment) + len(instruments) + len(streams)
status_counts = Counter()
for it in equipment + instruments:
    status_counts[it["verification_status"]] += 1

# equipment type distribution
eq_types = Counter(e["equipment_type"] for e in equipment)
# valve vs vessel separation
valves = [e for e in equipment if e["equipment_type"] == "Valve"]
vessels = [e for e in equipment if e["equipment_type"] == "Vessel"]
vamb = [e for e in equipment if e["equipment_type"] == "Vessel/Valve"]

lines = []
lines.append("# P&ID Verification & Cleanup Report")
lines.append("")
lines.append("## 1. Objective & method")
lines.append("")
lines.append("RAW P&ID -> VERIFIED STRUCTURED REPRESENTATION, performed locally on the sovereign "
             "stack (Qwen2.5-VL-3B on the CUDA llama-server at `:8003`, no cloud, no new model).")
lines.append("")
lines.append("Every candidate from the prior `equipment_registry.json` was re-checked against the "
             "original sheet: (a) a fine overlapping grid of crops located the tag visually; "
             "(b) a focused crop around the tag was used to confirm presence and resolve "
             "instrument-loop vs equipment and valve vs vessel ambiguity. Equipment *type* is "
             "derived from the ISA-style tag prefix written on the drawing (visually present), "
             "because the 3B model's free-text equipment typing was found unreliable. "
             "No information was invented; unreadable / unlocatable items are preserved as "
             "uncertain below.")
lines.append("")
lines.append("## 2. Errors found in the prior registry and how they were fixed")
lines.append("")
lines.append("| # | Prior error | Fix |")
lines.append("|---|---|---|")
rows = [
    ("Instrument loop tags (PIC-*, LT-*, TT-*, FT-*, PT-*) were classified as Pump / Tank / Other.",
     "Instrument prefixes are now detected BEFORE equipment prefixes; moved to `instrument_registry.json`."),
    ("Process-stream text labels were stored as equipment (e.g. 'CLARIFIED SOLUTION FROM CLARIFIER, SHEET 1').",
     "Moved to `stream_registry.json`."),
    ("Vessel/Valve ambiguity collapsed into one 'Vessel/Valve' bucket and asserted.",
     "Separated: valves -> equipment_type 'Valve'; vessels -> 'Vessel'; unresolved V-tags kept as 'Vessel/Valve' (uncertain)."),
    ("A/B duplicate variants counted as separate items (CP-1012A + CP-1012A/B, DP-1011A + DP-1011A/B, V-1013A + V-1013A/B/C).",
     "Consolidated to a single verified entry per physical item."),
    ("Model free-text mis-typing (C-1001 called Pump, GWA-51-371 called Valve, VBF-* called Valve, H-1001 called Vessel).",
     "Type taken from the tag prefix (C=Compressor, GWA=Grit Washer, VBF=Filter, H=Heater, ...)."),
    ("Several systems left as UNKNOWN and some asserted from model guess.",
     "UNKNOWN preserved where the title block was not visually confirmed; only 158.jpg yielded a clear plant name (Hydrogen Production Plant)."),
    ("Confidence values were asserted, not evidence-based.",
     "Now derived from visual grounding: >=2 crop agreements = verified (0.9), 1 = probable (0.8), prior-text-only / ambiguous = uncertain (0.5-0.6)."),
]
for i, (e, f) in enumerate(rows, 1):
    lines.append(f"| {i} | {e} | {f} |")
lines.append("")

# ---- registry summary ----
lines.append("## 3. Verified asset counts")
lines.append("")
lines.append(f"- Verified equipment (registry): **{len(equipment)}**")
lines.append(f"- Instruments (registry): **{len(instruments)}**")
lines.append(f"- Process streams (registry): **{len(streams)}**")
lines.append(f"- Total verified structured items: **{total}**")
lines.append(f"- Verification status: " + ", ".join(f"{k}={v}" for k, v in status_counts.most_common()))
lines.append("")
lines.append("### Equipment type distribution")
lines.append("")
for t, c in eq_types.most_common():
    lines.append(f"- {t}: {c}")
lines.append(f"- (Valves separated: {len(valves)} valve(s); Vessels: {len(vessels)}; "
             f"Vessel/Valve ambiguous/uncertain: {len(vamb)})")
lines.append("")

# ---- per-drawing table ----
lines.append("## 4. Per-drawing verification summary")
lines.append("")
lines.append("| Drawing | Plant/System | Equip | Verified | Probable | Uncertain | Instr | Streams |")
lines.append("|---|---|---|---|---|---|---|---|")
for d in DRAW:
    eqs = eq_d.get(d, [])
    ins = in_d.get(d, [])
    sts = st_d.get(d, [])
    plant = "Hydrogen Production Plant" if d == "158.jpg" else "UNKNOWN (not confirmed on title block)"
    nv = sum(1 for e in eqs if e["verification_status"] == "verified")
    np_ = sum(1 for e in eqs if e["verification_status"] == "probable")
    nu = sum(1 for e in eqs if e["verification_status"] == "uncertain")
    lines.append(f"| {d} | {plant} | {len(eqs)} | {nv} | {np_} | {nu} | {len(ins)} | {len(sts)} |")
lines.append("")

# ---- re-ranking ----
lines.append("## 5. Re-ranking after verification")
lines.append("")
lines.append("### 5.1 Best drawing for synthetic knowledge generation")
lines.append("")
lines.append("**158.jpg (Hydrogen Production Plant).** It is the only drawing whose plant name was "
             "visually confirmed on the title block, and it carries the highest proportion of "
             "visually *verified* equipment (C-1001 Compressor, P-1001 Pump, R-1001 Reactor, "
             "E-1005 Heat Exchanger, H-1001/1002 Heaters, V-1001/1002 Vessels, VBF-55-423 Filter, "
             "GWA-51-371 Grit Washer) plus verified instruments (LT-101, PIC-101). "
             "176.jpg has more raw items but its system is UNKNOWN and most of its entries are "
             "uncertain, so it is lower priority for knowledge generation.")
lines.append("")
lines.append("### 5.2 Best equipment candidate")
lines.append("")
lines.append("- **R-1001 (Reactor, 158.jpg, verified)** - central process equipment of the identified "
             "Hydrogen Plant; ideal SOP / maintenance / approval-note anchor.")
lines.append("- Runner-up: **C-1001 (Compressor, 158.jpg, verified)**.")
lines.append("")
lines.append("### 5.3 Best process chain (candidate)")
lines.append("")
lines.append("**158.jpg Hydrogen train:** P-1001 (feed Pump) -> R-1001 (Reactor) -> E-1005 "
             "(Heat Exchanger) -> C-1001 (Compressor) -> V-1001 (Vessel). All five are *verified* "
             "equipment on the same identified plant. NOTE: explicit pipe/line connections between "
             "them were NOT re-verified in this pass (the prior connection list came from 176.jpg); "
             "pipe routing should be confirmed visually before asserting a chain.")
lines.append("")
lines.append("### 5.4 Best equipment for a maintenance scenario")
lines.append("")
lines.append("- **P-1001 (Pump, 158.jpg, verified)** - rotating equipment with the highest maintenance "
             "demand and a verified tag; best maintenance-record / maintenance-SOP candidate.")
lines.append("")
lines.append("### 5.5 Best equipment for an inspection scenario")
lines.append("")
lines.append("- **V-1001 (Vessel, 158.jpg, verified)** and **R-1001 (Reactor, 158.jpg, verified)** - "
             "pressure vessels requiring periodic inspection; both visually verified.")
lines.append("")
lines.append("### 5.6 Best equipment for a sensor-data scenario")
lines.append("")
lines.append("- **LT-101 (Level Transmitter, 158.jpg, verified)** and **TT-1001 (Temperature Transmitter, "
             "176.jpg, verified)** - verified instrument loops that natively produce time-series sensor data.")
lines.append("")
lines.append("### 5.7 Best equipment for an approval-note scenario")
lines.append("")
lines.append("- **R-1001 (Reactor, 158.jpg, verified)** - capital process equipment on the identified plant; "
             "strongest approval-note / capital-change candidate.")
lines.append("")

# ---- preserved uncertain ----
lines.append("## 6. Preserved uncertain / unverified items (not deleted)")
lines.append("")
uncertain_eq = [e for e in equipment if e["verification_status"] == "uncertain"]
lines.append(f"### 6.1 Uncertain equipment ({len(uncertain_eq)})")
lines.append("")
lines.append("These were located only via the prior extraction (whole-sheet) or remain Vessel/Valve "
             "ambiguous; type/system NOT asserted. Require human verification before document generation:")
lines.append("")
for e in uncertain_eq:
    note = " (Vessel/Valve ambiguous)" if e["equipment_type"] == "Vessel/Valve" else ""
    lines.append(f"- {e['tag']} [{e['equipment_type']}]{note} - {e['source_drawing']} "
                 f"(conf={e['confidence']})")
lines.append("")
lines.append("### 6.2 Items whose system is UNKNOWN (preserved, not invented)")
lines.append("")
for d in ("176.jpg", "194.jpg", "196.jpg"):
    eqs = eq_d.get(d, [])
    if eqs:
        lines.append(f"- {d}: {len(eqs)} equipment, plant/system NOT confirmed on title block -> UNKNOWN.")
lines.append("")
lines.append("### 6.3 Process-stream descriptions (removed from equipment, preserved here)")
lines.append("")
for s in streams:
    lines.append(f"- \"{s['description']}\" ({s['source_drawing']})")
lines.append("")
lines.append("## 7. Deliverables produced")
lines.append("")
lines.append("- `registry/verified_equipment_registry.json` (schema: tag, equipment_type, system, "
             "source_drawing, location{x,y,width,height}, confidence, verification_status)")
lines.append("- `registry/instrument_registry.json` (schema: tag, instrument_type, source_drawing, "
             "confidence, verification_status)")
lines.append("- `registry/stream_registry.json` (schema: description, source_drawing, from, to, confidence)")
lines.append("- `reports/verification_report.md` (this file)")
lines.append("")
lines.append("No synthetic SOPs / manuals were generated, per instruction. The only output of this "
             "task is the verified structured representation above.")

open(os.path.join(ROOT, "reports", "verification_report.md"), "w", encoding="utf-8").write("\n".join(lines))
print("report written; equipment=%d instruments=%d streams=%d uncertain_eq=%d" %
      (len(equipment), len(instruments), len(streams), len(uncertain_eq)))
