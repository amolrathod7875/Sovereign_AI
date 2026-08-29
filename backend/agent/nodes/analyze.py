"""ANALYZE_EVIDENCE node: run sensor analysis and extract structured facts from
the retrieved documents (inspection findings, vendor parts, SOP requirements).
"""
import logging
import re
import time
from typing import Dict, Any, List

from agent.tools.analyze_csv import analyze_csv
from agent.utils import trace_entry, elapsed_ms

logger = logging.getLogger(__name__)


def _doc_content(docs: List[Dict[str, Any]], doc_type: str) -> str:
    for d in docs:
        if d.get("document_type") == doc_type:
            return d.get("content", "")
    return ""


def _extract_inspection_findings(text: str) -> List[Dict[str, Any]]:
    lowered = text.lower()
    findings: List[Dict[str, Any]] = []
    if "hotspot" in lowered or ("catalyst" in lowered and "deactivat" in lowered):
        findings.append({
            "type": "catalyst_hotspot",
            "value": "Catalyst-bed thermal hotspot / catalyst deactivation detected during inspection.",
            "source_document_type": "inspection_report",
        })
    if "thermowell" in lowered and "drift" in lowered:
        findings.append({
            "type": "thermowell_drift",
            "value": "Thermowell reading drift detected (sensor reference deviation).",
            "source_document_type": "inspection_report",
        })
    if "gasket" in lowered and "weep" in lowered:
        findings.append({
            "type": "gasket_weep",
            "value": "Top-head gasket weep (seepage) detected.",
            "source_document_type": "inspection_report",
        })
    # Fallback: surface any sentence containing "finding" / "abnormal".
    if not findings:
        for sent in re.split(r"(?<=[\.\!?])\s+", text):
            if any(k in sent.lower() for k in ("abnormal", "finding", "defect", "hotspot", "drift", "weep")):
                findings.append({"type": "observation", "value": sent.strip()[:300],
                                 "source_document_type": "inspection_report"})
    return findings


def _extract_vendor_parts(text: str) -> List[Dict[str, Any]]:
    parts = re.findall(r"HRS-[A-Z0-9-]+", text)
    seen = []
    for p in parts:
        if p not in [x["part_number"] for x in seen]:
            seen.append({"part_number": p, "source_document_type": "vendor_correspondence"})
    return seen


def _extract_sop_requirements(text: str) -> List[str]:
    lowered = text.lower()
    reqs: List[str] = []
    signals = {
        "controlled shutdown": "controlled shutdown",
        "esd": "emergency shutdown (ESD)",
        "reactor trip": "reactor trip",
        "catalyst change": "catalyst change-out",
        "gasket replacement": "gasket replacement",
        "thermowell recalibration": "thermowell recalibration",
        "approval": "maintenance approval gate",
    }
    for key, label in signals.items():
        if key in lowered and label not in reqs:
            reqs.append(label)
    return reqs


def run(state: dict) -> dict:
    start = time.time()
    docs = state.get("retrieved_documents", [])
    errors: List[str] = []

    # 1) Sensor analysis (programmatic)
    try:
        sensor = analyze_csv()
    except Exception as e:
        logger.error("analyze_csv failed: %s", e)
        sensor = {"error": str(e)}
        errors.append(f"analyze_csv:{e}")

    # 2) Extract structured facts
    inspection_text = _doc_content(docs, "inspection_report")
    inspection_findings = _extract_inspection_findings(inspection_text) if inspection_text else []

    vendor_text = _doc_content(docs, "vendor_correspondence")
    vendor_parts = _extract_vendor_parts(vendor_text) if vendor_text else []

    sop_text = (_doc_content(docs, "operating_sop") + "\n" +
                _doc_content(docs, "preventive_maintenance_sop"))
    sop_reqs = _extract_sop_requirements(sop_text)

    breached = bool(sensor.get("any_threshold_breach"))
    needs_calc = breached or any(sensor.get("breached_signals"))

    calculations: Dict[str, Any] = {
        "sensor_analysis": sensor,
        "inspection_findings": inspection_findings,
        "vendor_parts": vendor_parts,
        "sop_requirements": sop_reqs,
    }

    return {
        "calculations": calculations,
        "needs_calculation": bool(needs_calc),
        "errors": errors,
        "status": "ANALYZED",
        "trace": [trace_entry("analyze_evidence", "sensor_analysis+extract",
                              "analyze_csv,regex", elapsed_ms(start), "SUCCESS",
                              breached=breached, needs_calc=bool(needs_calc),
                              inspection_findings=len(inspection_findings),
                              vendor_parts=len(vendor_parts))],
    }
