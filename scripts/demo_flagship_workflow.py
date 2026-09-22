"""Phase 14B1 — Flagship Industrial Workflow demo harness.

Thin wrapper over the authoritative production entrypoint ``agent.run.run_agent_task``.
No independent RAG, no direct VLM calls, no calculations, no DOCX generation,
no decisions.  It simply invokes the real workflow and prints a judge-readable
summary plus a machine-readable validation result.

B1 does NOT run live GPU inference.
B2 will execute this script live against the local vision server.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from agent.run import run_agent_task  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PID_158 = str(REPO / "PID_Dataset" / "0__raw_data" / "sheets" / "test" / "158.jpg")
FLAGSHIP_TASK = (
    "Inspect P&ID 158.jpg for R-1001. Validate the asset identity, connect it to "
    "the local knowledge base, review the available inspection findings, sensor "
    "history, SOP requirements and vendor recommendations, independently verify "
    "required numerical analysis in the sandbox, and prepare a draft maintenance "
    "approval note using only local evidence."
)
FLAGSHIP_ASSET = "R-1001"
FLAGSHIP_ANALYSIS_TYPE = "pid"
FLAGSHIP_ARTIFACT = "R-1001_FLAGSHIP_DRAFT_APPROVAL.docx"
REPORTS_DIR = REPO / "reports"
LATEST_JSON = REPORTS_DIR / "flagship_workflow_latest.json"
LATEST_MD = REPORTS_DIR / "flagship_workflow_latest.md"


def validate_flagship_result(result: dict) -> list:
    checks = []
    asset_identity = result.get("asset_identity", {}) or {}

    checks.append(("asset_identity_verified",
                    asset_identity.get("status") == "VERIFIED"))
    checks.append(("canonical_asset_correct",
                    asset_identity.get("canonical_tag") == FLAGSHIP_ASSET))
    checks.append(("only_canonical_asset_retrieved",
                    result.get("retrieval_summary", {}).get("unique_asset_tags") == [FLAGSHIP_ASSET]))
    checks.append(("hybrid_rag_used",
                    bool(result.get("retrieval_summary", {}).get("retrieval_modes"))))
    calc = result.get("calculations_summary", {}) or {}
    checks.append(("sensor_breach_present",
                    bool(calc.get("any_threshold_breach"))))
    checks.append(("inspection_evidence_present",
                    bool(calc.get("inspection_findings"))))
    checks.append(("vendor_evidence_present",
                    bool(calc.get("vendor_parts"))))
    checks.append(("sop_evidence_present",
                    bool(calc.get("sop_requirements"))))
    checks.append(("sandbox_executed",
                    bool(calc.get("sandbox_used"))))
    checks.append(("approval_required",
                    result.get("approval_required") is True))
    checks.append(("artifact_created",
                    bool(result.get("artifacts"))))
    ver = result.get("verification", {}) or {}
    checks.append(("artifact_verified",
                    ver.get("ok") is True))
    checks.append(("external_calls_zero",
                    result.get("external_calls", -1) == 0))
    trace = result.get("trace", []) or []
    required_nodes = [
        "plan", "vision_analysis", "asset_identity", "retrieve_evidence",
        "analyze_evidence", "needs_calculation", "python_analysis",
        "synthesize_findings", "make_decision", "generate_approval_note",
        "verify_output",
    ]
    trace_nodes = [t.get("node") for t in trace]
    checks.append(("trace_complete", all(n in trace_nodes for n in required_nodes)))
    return checks


def summarize(result: dict) -> str:
    asset_identity = result.get("asset_identity", {}) or {}
    retrieval = result.get("retrieval_summary", {}) or {}
    calc = result.get("calculations_summary", {}) or {}
    ver = result.get("verification", {}) or {}
    trace = result.get("trace", []) or []

    lines = []
    lines.append("=" * 72)
    lines.append("SOVEREIGN AI — FLAGSHIP INDUSTRIAL WORKFLOW")
    lines.append("=" * 72)
    lines.append("")
    lines.append("1. ASSET IDENTITY")
    lines.append(f"   Requested  : {asset_identity.get('requested_tag', 'n/a')}")
    lines.append(f"   Canonical  : {asset_identity.get('canonical_tag', 'n/a')}")
    lines.append(f"   Status     : {asset_identity.get('status', 'n/a')}")
    lines.append(f"   Vision tags: {asset_identity.get('vision_tags', [])}")
    lines.append("")
    lines.append("2. LOCAL KNOWLEDGE")
    lines.append(f"   Retrieval mode : {retrieval.get('retrieval_modes', [])}")
    lines.append(f"   Chunks         : {retrieval.get('chunk_count', 0)}")
    lines.append(f"   Source files   : {retrieval.get('source_files', [])}")
    lines.append(f"   Unique assets  : {retrieval.get('unique_asset_tags', [])}")
    lines.append("")
    lines.append("3. INDUSTRIAL FINDINGS")
    lines.append(f"   Sensor breaches     : {calc.get('any_threshold_breach')}")
    lines.append(f"   Inspection findings : {calc.get('inspection_findings', [])}")
    lines.append(f"   Vendor parts        : {calc.get('vendor_parts', [])}")
    lines.append(f"   SOP requirements    : {calc.get('sop_requirements', [])}")
    lines.append("")
    lines.append("4. SANDBOX VERIFICATION")
    lines.append(f"   Executed : {calc.get('sandbox_used')}")
    py = calc.get("python_analysis", {}) or {}
    lines.append(f"   Result   : {py.get('breach_summary') or py.get('raw')}")
    lines.append("")
    lines.append("5. DECISION")
    lines.append(f"   Decision         : {result.get('decision')}")
    lines.append(f"   Approval required: {result.get('approval_required')}")
    lines.append(f"   Required actions : {result.get('required_actions', [])}")
    lines.append("")
    lines.append("6. ARTIFACT")
    artifacts = result.get("artifacts", []) or []
    lines.append(f"   Path             : {artifacts[0] if artifacts else 'n/a'}")
    lines.append(f"   Verified         : {ver.get('ok')}")
    lines.append(f"   Draft status     : DRAFT — pending human authorization")
    lines.append("")
    lines.append("7. SOVEREIGNTY")
    lines.append(f"   External calls   : {result.get('external_calls', -1)}")
    lines.append(f"   Routing          : {result.get('routing', {}).get('selected_model', 'n/a')}")
    lines.append(f"   Models used      : {result.get('routing', {}).get('models_required', [])}")
    lines.append("")
    lines.append("8. EXECUTION TRACE")
    for t in trace:
        lines.append(f"   {t.get('node')} -> {t.get('action')} [{t.get('status')}] "
                     f"({t.get('tool')}) {t.get('duration_ms')}ms")
    lines.append("=" * 72)
    return "\n".join(lines)


def _sanitize_artifacts(artifacts):
    out = []
    for a in artifacts or []:
        try:
            out.append(str(Path(a).relative_to(REPO)))
        except Exception:
            out.append(Path(a).name)
    return out


def write_reports(result: dict, checks: list) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    failed = [name for name, ok in checks if not ok]
    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "run_id": result.get("run_id"),
        "status": result.get("status"),
        "asset_identity": result.get("asset_identity"),
        "retrieval_summary": result.get("retrieval_summary"),
        "calculations_summary": {
            k: v for k, v in result.get("calculations_summary", {}).items()
            if k != "python_analysis"
        },
        "decision": result.get("decision"),
        "approval_required": result.get("approval_required"),
        "artifacts": _sanitize_artifacts(result.get("artifacts")),
        "verification": result.get("verification"),
        "external_calls": result.get("external_calls"),
        "flagship_validation": {
            "passed": not failed,
            "failed": failed,
            "checks": {name: ok for name, ok in checks},
        },
    }
    LATEST_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    md = [
        f"# Flagship Workflow Report",
        f"_Generated: {payload['timestamp']}_",
        "",
        f"- Run ID: {payload['run_id']}",
        f"- Status: {payload['status']}",
        f"- Asset: {result.get('asset_identity', {}).get('canonical_tag')}",
        f"- Approval required: {payload['approval_required']}",
        f"- External calls: {payload['external_calls']}",
        f"- Validation: {'PASS' if not failed else 'FAIL'}",
    ]
    if failed:
        md.append(f"- Failed checks: {', '.join(failed)}")
    md.extend(["", "## Flagship Validation", "",
               "| Check | Result |",
               "|-------|--------|"] + [f"| {n} | {'PASS' if ok else 'FAIL'} |" for n, ok in checks])
    LATEST_MD.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> int:
    print("=" * 72)
    print("SOVEREIGN AI — FLAGSHIP INDUSTRIAL WORKFLOW")
    print("=" * 72)
    print(f"\nTask      : {FLAGSHIP_TASK}")
    print(f"Asset     : {FLAGSHIP_ASSET}")
    print(f"Image     : {PID_158}")
    print(f"Artifact  : {FLAGSHIP_ARTIFACT}")
    print()

    if not os.path.exists(PID_158):
        print(f"ERROR: image not found: {PID_158}")
        return 2

    try:
        result = run_agent_task(
            FLAGSHIP_TASK,
            asset_tag=FLAGSHIP_ASSET,
            image_path=PID_158,
            analysis_type=FLAGSHIP_ANALYSIS_TYPE,
            artifact_filename=FLAGSHIP_ARTIFACT,
        )
    except Exception as e:
        print(f"ERROR: workflow failed: {e}")
        return 3

    checks = validate_flagship_result(result)
    print(summarize(result))
    print("\nVALIDATION")
    print("-" * 72)
    failed = []
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed.append(name)
        print(f"  {name}: {status}")
    print("-" * 72)
    if failed:
        print(f"\nFAILED checks: {', '.join(failed)}")
        return 1
    print("\nAll flagship checks PASSED.")

    try:
        write_reports(result, checks)
        print(f"\nReports written:")
        print(f"  JSON: {LATEST_JSON}")
        print(f"  Markdown: {LATEST_MD}")
    except Exception as e:
        print(f"\nWARNING: report write failed: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
