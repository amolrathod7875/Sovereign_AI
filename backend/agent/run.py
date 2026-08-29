"""Agent runner: execute the graph with network sovereignty enforced."""
import logging
import uuid
from typing import Dict, Any

from agent.state import create_initial_state
from agent.graph import GRAPH
from agent.security.netguard import no_network
from agent.config import OUTPUT_DIR

logger = logging.getLogger(__name__)


def run_agent_task(task: str, asset_tag: str = "R-1001", run_id: str = None,
                   artifact_filename: str = None) -> Dict[str, Any]:
    """Run the full maintenance-agent workflow.

    Returns a serialisable result dict including the final state, decision,
    artifacts and a guarantee of zero external network calls.

    ``artifact_filename`` optionally overrides the generated DOCX filename so a
    new version can be produced without overwriting an existing artifact.
    """
    run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
    initial = create_initial_state(run_id, task, asset_tag)
    if artifact_filename:
        initial["artifact_filename"] = artifact_filename

    with no_network() as guard:
        final = GRAPH.invoke(initial)
    final["external_calls"] = guard.external_calls

    decision = final.get("decision", {})
    evidence = [
        {"claim": e.get("claim"), "source": e.get("source_file"),
         "document_type": e.get("document_type"), "confidence": e.get("confidence")}
        for e in final.get("evidence", [])
    ]

    return {
        "run_id": run_id,
        "status": final.get("status", "UNKNOWN"),
        "decision": decision.get("decision"),
        "reasoning_summary": decision.get("reasoning_summary"),
        "approval_required": decision.get("approval_required", False),
        "required_actions": decision.get("required_actions", []),
        "supporting_evidence": decision.get("supporting_evidence", []),
        "artifacts": final.get("artifacts", []),
        "evidence": evidence,
        "findings": final.get("findings", []),
        "calculations_summary": _calc_summary(final.get("calculations", {})),
        "external_calls": final.get("external_calls", 0),
        "trace": final.get("trace", []),
        "errors": final.get("errors", []),
        "verification": final.get("verification", {}),
        "output_dir": str(OUTPUT_DIR),
    }


def _calc_summary(calc: Dict[str, Any]) -> Dict[str, Any]:
    sensor = calc.get("sensor_analysis", {})
    out = {
        "any_threshold_breach": sensor.get("any_threshold_breach"),
        "breached_signals": sensor.get("breached_signals"),
        "signals": {
            k: {
                "max": v.get("max"), "mean": v.get("mean"),
                "n_breach_high": v.get("n_breach_high"),
                "first_breach_high": v.get("first_breach_high"),
                "last_breach_high": v.get("last_breach_high"),
            } for k, v in sensor.get("signals", {}).items()
        },
        "inspection_findings": [f.get("type") for f in calc.get("inspection_findings", [])],
        "vendor_parts": [p.get("part_number") for p in calc.get("vendor_parts", [])],
        "sop_requirements": calc.get("sop_requirements", []),
        "python_analysis": calc.get("python_analysis"),
    }
    return out
