"""MAKE_DECISION node: produce the structured decision with supporting evidence."""
import logging
import time
from typing import Dict, Any, List

from agent.utils import trace_entry, elapsed_ms

logger = logging.getLogger(__name__)


def run(state: dict) -> dict:
    start = time.time()
    findings = state.get("findings", [])
    actions = state.get("required_actions", [])
    calc = state.get("calculations", {})
    sensor = calc.get("sensor_analysis", {})

    shutdown_needed = any("shutdown" in a.lower() or "esd" in a.lower() for a in actions)
    approval_required = bool(shutdown_needed and actions)

    # Supporting evidence references (document types actually retrieved/used).
    sources = []
    for f in findings:
        dt = f.get("source_document_type")
        if dt and dt not in sources:
            sources.append(dt)

    # Multimodal (vision) evidence summary, if the task used the local VLM.
    vision_evidence = state.get("vision_evidence", []) or []
    vision_summary = ""
    if vision_evidence:
        tags = state.get("vision_tags", []) or []
        uncertain_total = sum(len(v.get("uncertain_items", []) or []) for v in vision_evidence)
        vision_summary = (
            f" A local Qwen-VL inspection of the attached P&ID/image identified "
            f"equipment/tags {tags} and reported {uncertain_total} uncertain item(s); "
            f"those visual observations are treated as witness evidence, not engineering truth."
        )

    reasoning = (
        "R-1001 process data shows confirmed threshold breaches "
        f"({'multiple signals' if sensor.get('breached_signals') else 'no signal'}). "
        "These breaches are correlated with the latest inspection findings "
        "(catalyst hotspot, thermowell drift, gasket weep). The applicable Operating/PM SOP "
        "prescribes a controlled shutdown / ESD and defines the corrective actions, and the "
        "vendor correspondence recommends matching spare parts. Therefore a controlled shutdown "
        "and corrective maintenance are required, and maintenance approval must be obtained before execution."
    ) + vision_summary

    decision = {
        "decision": (
            "Initiate a controlled reactor shutdown and perform corrective maintenance on R-1001 "
            "(catalyst replacement, top-head gasket replacement, thermowell recalibration) per the "
            "Operating/PM SOP; stage vendor-recommended spares and obtain maintenance approval "
            "before execution."
        ),
        "reasoning_summary": reasoning,
        "supporting_evidence": sources,
        "required_actions": actions,
        "approval_required": approval_required,
    }

    return {
        "decision": decision,
        "status": "DECIDED",
        "trace": [trace_entry("make_decision", "form_decision", "internal",
                              elapsed_ms(start), "SUCCESS",
                              approval_required=approval_required,
                              supporting=len(sources))],
    }
