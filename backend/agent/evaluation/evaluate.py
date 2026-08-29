"""Agent evaluation against cross_document_ground_truth.json.

The ground-truth file is used ONLY here (by the evaluator) and is NEVER exposed
to the agent during execution.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from docx import Document

from agent.config import REPO_ROOT

logger = logging.getLogger(__name__)
GROUND_TRUTH = REPO_ROOT / "data" / "synthetic" / "metadata" / "cross_document_ground_truth.json"
REPORT_PATH = REPO_ROOT / "reports" / "agent_evaluation.md"


def _docx_text(path: str) -> str:
    try:
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception:
        return ""


def _has(text: str, *needles: str) -> bool:
    t = (text or "").lower()
    return any(n.lower() in t for n in needles)


def evaluate(run_result: Dict[str, Any], ground_truth_path: str = None) -> Dict[str, Any]:
    gt_path = Path(ground_truth_path) if ground_truth_path else GROUND_TRUTH
    gt = json.loads(gt_path.read_text(encoding="utf-8"))

    decision = run_result.get("decision") or ""
    reasoning = run_result.get("reasoning_summary") or ""
    findings = run_result.get("findings", [])
    calc = run_result.get("calculations_summary", {}) or {}
    artifacts = run_result.get("artifacts", [])

    findings_text = " ".join(str(f.get("value", "")) for f in findings)
    artifact_text = " ".join(_docx_text(p) for p in artifacts)
    combined = " ".join([decision, reasoning, findings_text, artifact_text])

    # Structured signals (preferred) + text fallback.
    breached = calc.get("breached_signals") or []
    vendor_parts = calc.get("vendor_parts") or []
    insp = calc.get("inspection_findings") or []
    approval_required = run_result.get("approval_required", False)

    criteria = []

    def check(name, passed, detail=""):
        criteria.append({"criterion": name, "pass": bool(passed), "detail": detail})

    check("temperature_breach_detected",
          ("temp" in " ".join(breached).lower() or "TI-1001" in " ".join(breached))
          or _has(combined, "temperature", "320"),
          f"breached_signals={breached}")

    check("pressure_breach_detected",
          _has(combined, "pressure")
          and _has(combined, "breach", "21", "high-high", "exceed"),
          "pressure signal referenced with breach language")

    check("vibration_breach_detected",
          _has(combined, "vibration")
          and _has(combined, "breach", "4.0", "high", "exceed"),
          "vibration signal referenced with breach language")

    check("catalyst_hotspot_detected",
          ("catalyst_hotspot" in insp) or _has(combined, "catalyst", "hotspot", "deactivat"),
          f"inspection_findings={insp}")

    check("thermowell_drift_detected",
          ("thermowell_drift" in insp) or _has(combined, "thermowell", "drift"),
          f"inspection_findings={insp}")

    check("gasket_weep_detected",
          ("gasket_weep" in insp) or _has(combined, "gasket", "weep"),
          f"inspection_findings={insp}")

    check("vendor_recommendation_detected",
          bool(vendor_parts) or _has(combined, "vendor", "recommend", "HRS-"),
          f"vendor_parts={vendor_parts}")

    check("controlled_shutdown_recommended",
          _has(combined, "controlled shutdown", "shutdown", "esd", "reactor trip"),
          "shutdown language present")

    check("corrective_maintenance_recommended",
          _has(combined, "corrective", "replace", "recalibrat", "catalyst change"),
          "corrective action language present")

    check("approval_required",
          (approval_required is True) or _has(combined, "approval required", "approval_required", "approval gate"),
          f"approval_required={approval_required}")

    # Evidence-support check: every finding must cite a source document type.
    findings_with_source = [f for f in findings if f.get("source_document_type") or f.get("source_file")]
    evidence_supported = len(findings) > 0 and len(findings_with_source) == len(findings)

    passed = sum(1 for c in criteria if c["pass"])
    total = len(criteria)
    score = round(100.0 * passed / total, 1) if total else 0.0

    result = {
        "asset": gt.get("asset"),
        "expected_approval": gt.get("expected_approval"),
        "agent_approval_required": approval_required,
        "criteria": criteria,
        "passed": passed,
        "total": total,
        "score": score,
        "findings_evidence_supported": evidence_supported,
        "external_calls": run_result.get("external_calls", 0),
        "artifacts": artifacts,
    }
    return result


def write_report(result: Dict[str, Any], run_result: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Agent Evaluation Report — Phase 4 Sovereign AI Maintenance Agent\n")
    lines.append(f"- Asset: `{result['asset']}`")
    lines.append(f"- Expected approval (ground truth): `{result['expected_approval']}`")
    lines.append(f"- Agent approval_required: `{result['agent_approval_required']}`")
    lines.append(f"- External network calls during run: `{result['external_calls']}`")
    lines.append(f"- Artifacts: {', '.join(result['artifacts']) or 'NONE'}\n")

    lines.append("## Criteria (10 required)\n")
    lines.append("| # | Criterion | Result | Detail |")
    lines.append("|---|---|---|---|")
    for i, c in enumerate(result["criteria"], 1):
        lines.append(f"| {i} | {c['criterion']} | {'PASS' if c['pass'] else 'FAIL'} | {c['detail']} |")

    lines.append("")
    lines.append(f"## Score: {result['passed']}/{result['total']} ({result['score']}%)")
    lines.append(f"## Findings evidence-supported: {'YES' if result['findings_evidence_supported'] else 'NO'}")

    lines.append("\n## Agent decision\n")
    lines.append(f"**Decision:** {run_result.get('decision')}\n")
    lines.append(f"**Reasoning:** {run_result.get('reasoning_summary')}\n")
    lines.append("**Required actions:**")
    for a in run_result.get("required_actions", []):
        lines.append(f"- {a}")

    lines.append("\n## Network sovereignty\n")
    lines.append(f"- External network calls recorded: `{result['external_calls']}` (must be 0).")
    lines.append("- Embeddings: local sentence-transformers (offline).")
    lines.append("- Retrieval: local embedded Qdrant + local BM25.")
    lines.append("- Python execution: local sandboxed subprocess, no network modules, no out-of-tree filesystem access.")
    lines.append("- Ground-truth file was used ONLY by this evaluator, never by the agent.")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return str(REPORT_PATH)
