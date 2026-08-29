"""SYNTHESIZE_FINDINGS node: chain the evidence into a coherent finding set.

Establishes the cross-document reasoning chain required by the task:
  sensor anomaly -> inspection finding -> applicable SOP requirement ->
  vendor recommendation -> corrective action -> approval requirement.
"""
import logging
import time
from typing import Dict, Any, List

from agent.utils import trace_entry, elapsed_ms

logger = logging.getLogger(__name__)


def run(state: dict) -> dict:
    start = time.time()
    calc = state.get("calculations", {})
    sensor = calc.get("sensor_analysis", {})
    inspection = calc.get("inspection_findings", [])
    vendor = calc.get("vendor_parts", [])
    sop = calc.get("sop_requirements", [])

    findings: List[Dict[str, Any]] = []
    required_actions: List[str] = []

    # 1) Sensor anomaly
    signals = sensor.get("signals", {})
    breach_lines = []
    for col, s in signals.items():
        if s.get("n_breach_high"):
            breach_lines.append(
                f"{s['label']} ({s['tag']}) breached HIGH at {s['max']} {s['unit']} "
                f"(first {s.get('first_breach_high')}, last {s.get('last_breach_high')}); "
                f"HH breaches: {s.get('n_breach_high_high', 0)}."
            )
    if breach_lines:
        findings.append({
            "claim": "sensor_anomaly",
            "value": "Threshold breaches detected in R-1001 process data: " + " ".join(breach_lines),
            "source_document_type": "sensor_dataset",
        })

    # 2) Inspection linkage
    for f in inspection:
        findings.append({
            "claim": f.get("type", "inspection_finding"),
            "value": f.get("value", ""),
            "source_document_type": "inspection_report",
        })

    # 3) SOP requirement
    if sop:
        findings.append({
            "claim": "sop_requirement",
            "value": "Applicable SOP requirements identified: " + ", ".join(sop) + ".",
            "source_document_type": "operating_sop",
        })

    # 4) Vendor recommendation
    if vendor:
        parts = ", ".join(p["part_number"] for p in vendor)
        findings.append({
            "claim": "vendor_recommendation",
            "value": f"Vendor recommends spare parts: {parts}.",
            "source_document_type": "vendor_correspondence",
        })

    # 4b) Vision (multimodal) evidence — from the local Qwen-VL tool.
    vision_evidence = state.get("vision_evidence", []) or []
    vision_uncertain: List[str] = []
    for ve in vision_evidence:
        if not isinstance(ve, dict):
            continue
        src = ve.get("source_file", "image")
        for f in ve.get("findings", []) or []:
            findings.append({
                "claim": "vision_finding",
                "value": f"[VISION] {f}",
                "source_document_type": "pid_drawing",
                "source_file": src,
            })
        for e in ve.get("entities", []) or []:
            name = e.get("name") if isinstance(e, dict) else str(e)
            findings.append({
                "claim": "vision_entity",
                "value": f"[VISION] Identified {name}",
                "source_document_type": "pid_drawing",
                "source_file": src,
            })
        vision_uncertain.extend(ve.get("uncertain_items", []) or [])

    # 5) Corrective action
    shutdown_needed = any(k in " ".join(sop).lower() for k in ("shutdown", "esd", "trip"))
    if shutdown_needed:
        required_actions.append("Initiate controlled reactor shutdown (ESD per Operating SOP); "
                               "do not restart until the high-high event is closed.")
    for f in inspection:
        t = f.get("type")
        if t == "catalyst_hotspot":
            required_actions.append("Replace catalyst charge (deactivated / hotspot).")
        elif t == "thermowell_drift":
            required_actions.append("Recalibrate / replace reactor thermowell assembly.")
        elif t == "gasket_weep":
            required_actions.append("Replace top-head gasket kit (weep / seepage).")
    for p in vendor:
        required_actions.append(f"Procure / stage recommended spare: {p['part_number']}.")

    # 6) Approval requirement (derived, not copied from ground truth)
    approval_required = bool(shutdown_needed and (vendor or inspection))
    if approval_required:
        required_actions.append("Obtain maintenance approval (controlled shutdown + spare parts) "
                                "before executing corrective work.")

    return {
        "findings": findings,
        "required_actions": required_actions,
        "status": "SYNTHESIZED",
        "trace": [trace_entry("synthesize_findings", "reason_chain", "internal",
                              elapsed_ms(start), "SUCCESS",
                              findings=len(findings), actions=len(required_actions),
                              approval_required=approval_required)],
    }
