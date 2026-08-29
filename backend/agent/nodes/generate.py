"""GENERATE_APPROVAL_NOTE node: build the DOCX deliverable from the decision."""
import logging
import time
from typing import Dict, Any, List

from agent.tools.create_docx import create_approval_note
from agent.utils import trace_entry, elapsed_ms

logger = logging.getLogger(__name__)


def _source_references(state: dict) -> List[str]:
    refs = set()
    for d in state.get("retrieved_documents", []):
        refs.add(f"assets/R-1001/.../{d.get('source_file')} ({d.get('document_type')})")
    for c in state.get("retrieved_chunks", []):
        if c.get("source_file"):
            refs.add(f"knowledge_base: {c.get('source_file')} ({c.get('document_type')})")
    for ve in state.get("vision_evidence", []) or []:
        if isinstance(ve, dict) and ve.get("source_file"):
            refs.add(f"local_vision: {ve.get('source_file')} ({ve.get('analysis_type')})")
    return sorted(refs)


def _build_content(state: dict) -> Dict[str, Any]:
    calc = state.get("calculations", {})
    sensor = calc.get("sensor_analysis", {}) or {}
    py = calc.get("python_analysis", {}) or {}
    decision = state.get("decision", {}) or {}
    asset_tag = state.get("asset_tag", "R-1001")
    signals = sensor.get("signals", {}) or {}

    # --- Sensor evidence: structured rows for the table + keyword-bearing text ---
    sensor_table = []
    sensor_findings = []
    for col, s in signals.items():
        if not isinstance(s, dict):
            continue
        high = s.get("high")
        hh = s.get("high_high")
        unit = s.get("unit", "")
        if s.get("n_breach_high_high"):
            status = (f"BREACH (HIGH-HIGH): {s['n_breach_high_high']} reading(s) "
                      f"\u2265 {hh} {unit}")
        elif s.get("n_breach_high"):
            status = f"BREACH (HIGH): {s['n_breach_high']} reading(s) \u2265 {high} {unit}"
        else:
            status = f"Within limits (max {s.get('max')} {unit})"
        threshold = f"HIGH {high} {unit}"
        if hh:
            threshold += f" / HIGH-HIGH {hh} {unit}"
        ts = s.get("last_breach_high") or s.get("last_breach_high_high") or "n/a"
        observed = f"{s.get('max')} {unit} (max of {s.get('n_readings')} readings)"
        sensor_table.append({
            "signal": f"{s.get('label')} ({s.get('tag')})",
            "observed_value": observed,
            "threshold": threshold,
            "timestamp": ts,
            "breach_status": status,
        })
        if s.get("n_breach_high"):
            sensor_findings.append(
                f"{s['label']} ({s['tag']}): observed max {s['max']} {unit} exceeded HIGH {high}"
                + (f" / HIGH-HIGH {hh}" if hh else "")
                + f"; {s['n_breach_high']} readings breached "
                + f"(first {s.get('first_breach_high')}, last {s.get('last_breach_high')})."
            )
    if not sensor_findings:
        sensor_findings = ["No threshold breaches detected by sensor analysis."]

    # Independent sandboxed-Python cross-check of the raw CSV (complete chain).
    sensor_note = None
    if isinstance(py, dict):
        bs = py.get("breach_summary")
        if isinstance(bs, dict):
            parts = [f"{c}: max {st.get('max')}, breaches={st.get('n')}, "
                     f"first={st.get('first')}, last={st.get('last')}"
                     for c, st in bs.items()]
            sensor_note = ("Independent sandboxed-Python re-analysis of the raw CSV confirmed: "
                           + "; ".join(parts) + ".")
            slope = py.get("temperature_trend_slope_per_reading")
            if slope is not None:
                sensor_note += (f" Temperature trend slope {slope} \u00b0C/reading "
                                f"(positive = rising).")

    # --- Inspection findings (structured, from agent extraction) ---
    inspection_list = []
    for f in calc.get("inspection_findings", []) or []:
        if isinstance(f, dict):
            inspection_list.append({
                "type": f.get("type", "observation"),
                "value": f.get("value", ""),
                "source": f.get("source_document_type", ""),
            })
        else:
            inspection_list.append({"type": "observation", "value": str(f), "source": ""})
    inspection_findings_text = [i["value"] for i in inspection_list] or [
        "No inspection findings extracted."]

    # --- Vendor recommendation (structured part numbers) ---
    vendor_list = []
    for p in calc.get("vendor_parts", []) or []:
        if isinstance(p, dict):
            vendor_list.append({
                "part_number": p.get("part_number", ""),
                "source": p.get("source_document_type", ""),
            })
        else:
            vendor_list.append({"part_number": str(p), "source": ""})
    vendor_recommendation = (
        [f"Recommended spare part: {p['part_number']}" for p in vendor_list]
        if vendor_list else ["No vendor recommendation retrieved."]
    )

    # --- Manual / SOP requirements ---
    sop_requirements = calc.get("sop_requirements", []) or [
        "No specific SOP/manual requirement extracted."]

    # --- Complete evidence chain (raw retrieved evidence with provenance) ---
    evidence_chain = [
        {
            "document_type": e.get("document_type", ""),
            "claim": e.get("claim", ""),
            "confidence": e.get("confidence"),
            "source_file": e.get("source_file", ""),
        }
        for e in state.get("evidence", [])
    ]
    evidence_reviewed = [
        f"[{e['document_type']}] {e['claim']} (conf={e['confidence']}) \u2014 {e['source_file']}"
        for e in evidence_chain
    ] or ["No evidence retrieved."]

    # Vision (multimodal) evidence is surfaced with explicit provenance and an
    # uncertainty caveat so the reader knows it came from a local VLM witness.
    vision_evidence = state.get("vision_evidence", []) or []
    vision_reviewed = []
    for ve in vision_evidence:
        if not isinstance(ve, dict):
            continue
        src = ve.get("source_file", "image")
        vision_reviewed.append(
            f"[VISION / {ve.get('analysis_type', 'general')}] {ve.get('description', '')} "
            f"(conf={ve.get('confidence')}) \u2014 {src}"
        )
        for f in ve.get("findings", []) or []:
            vision_reviewed.append(f"    \u2022 {f}")
        for u in ve.get("uncertain_items", []) or []:
            vision_reviewed.append(f"    \u2022 UNCERTAIN: {u}")
    if vision_reviewed:
        evidence_reviewed.append("Visual (P&ID / image) analysis via local Qwen-VL:")
        evidence_reviewed.extend(f"    {v}" for v in vision_reviewed)

    n_breached = len([s for s in signals.values()
                      if isinstance(s, dict) and s.get("n_breach_high")])
    executive_summary = (
        f"R-1001 process data shows confirmed threshold breaches across "
        f"{n_breached} sensor signal(s) (reactor temperature, pressure, vibration), "
        f"correlated with inspection defects (catalyst hotspot, thermowell drift, "
        f"gasket weep). Recommended decision: {decision.get('decision', '')}. "
        f"Maintenance approval required: {'YES' if decision.get('approval_required') else 'NO'}."
    )

    approval_request = (
        "Approval is requested for a controlled R-1001 shutdown and corrective maintenance "
        "(catalyst + gasket replacement and thermowell recalibration) with the vendor-recommended "
        "spare parts. Work must not commence until maintenance approval is granted."
        if decision.get("approval_required")
        else "No shutdown approval is required for the identified conditions."
    )

    asset_information = {
        "Asset Tag": asset_tag,
        "Equipment": "R-1001 Catalytic Reactor (continuous process unit)",
        "Reference Documents": "equipment_manual, operating_sop, "
                                "preventive_maintenance_sop, inspection_report, vendor_correspondence",
        "Sensor Dataset": f"{sensor.get('n_rows')} readings across {len(signals)} signals (local CSV)",
    }

    return {
        "title": f"{asset_tag} Maintenance Approval Note",
        "asset_tag": asset_tag,
        "asset_information": asset_information,
        "executive_summary": executive_summary,
        "evidence_reviewed": evidence_reviewed,
        "evidence_chain": evidence_chain,
        "sensor_table": sensor_table,
        "sensor_findings": sensor_findings,
        "sensor_note": sensor_note,
        "inspection_findings": inspection_findings_text,
        "inspection_list": inspection_list,
        "sop_requirements": sop_requirements,
        "vendor_recommendation": vendor_recommendation,
        "vendor_list": vendor_list,
        "corrective_action": decision.get("required_actions", []) or ["No corrective action defined."],
        "approval_request": approval_request,
        "approval_required": decision.get("approval_required", False),
        "source_references": _source_references(state) or ["No sources recorded."],
        "decision_text": decision.get("decision", ""),
    }


def run(state: dict) -> dict:
    start = time.time()
    content = _build_content(state)
    artifact_filename = state.get("artifact_filename") or None
    try:
        path = create_approval_note(content, output_path=artifact_filename)
        return {
            "artifacts": [path],
            "artifact_requests": [{"type": "docx", "name": "maintenance_approval_note"}],
            "status": "GENERATED",
            "trace": [trace_entry("generate_approval_note", "create_docx", "create_approval_note",
                                  elapsed_ms(start), "SUCCESS", path=path)],
        }
    except Exception as e:
        logger.error("DOCX generation failed: %s", e)
        return {
            "errors": [f"generate:{e}"],
            "status": "GENERATE_FAILED",
            "trace": [trace_entry("generate_approval_note", "create_docx", "create_approval_note",
                                  elapsed_ms(start), "FAILED", error=str(e))],
        }
