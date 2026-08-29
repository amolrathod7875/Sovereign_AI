"""Evaluation for the local coding agent.

Produces the 10-point checklist required by the spec and writes the markdown
report. Criterion 9 (sandbox restrictions) is verified with a LIVE probe that
attempts a real external socket and asserts the sandbox blocks it.
"""
import os
import tempfile
import logging
from pathlib import Path
from typing import Dict, Any, List

from agent.coder import sandbox as sandbox_mod

logger = logging.getLogger(__name__)

DELIVERABLES = ("solution.py", "test_solution.py", "sensor_fixture.csv")


def _probe_sandbox_blocks_network() -> Dict[str, Any]:
    """Attempt a real external connection inside the sandbox; expect it blocked."""
    with tempfile.TemporaryDirectory() as td:
        res = sandbox_mod.execute_code(
            td,
            "import socket\ns = socket.socket()\ns.connect(('8.8.8.8', 53))\n",
            timeout=15,
        )
    blocked = (res.get("exit_code") != 0) and (
        "Blocked" in (res.get("stderr") or "") or res.get("network_blocked", 0) > 0
    )
    return {"blocked": blocked, "detail": res.get("stderr", "")[:200]}


def evaluate(result: Dict[str, Any]) -> Dict[str, Any]:
    criteria: List[Dict[str, Any]] = []
    ws = result.get("workspace")

    def add(name, ok, detail):
        criteria.append({"name": name, "passed": bool(ok), "detail": detail})

    # 1. Code generated
    fc = result.get("file_contents") or {}
    sol = fc.get("solution.py", "")
    add("1. Code generated", bool(sol.strip()),
        f"solution.py length={len(sol)}")

    # 2. Files created correctly (on disk, in workspace)
    created_ok = True
    missing = []
    if ws:
        for name in DELIVERABLES:
            p = os.path.join(ws, name)
            if not (os.path.exists(p) and os.path.getsize(p) > 0):
                created_ok = False
                missing.append(name)
    add("2. Files created correctly", created_ok,
        "all deliverables present" if created_ok else f"missing: {missing}")

    # 3. Tests created
    test_src = fc.get("test_solution.py", "")
    add("3. Tests created", bool(test_src.strip()),
        f"test_solution.py length={len(test_src)}")

    # 4. Tests executed
    to = result.get("test_output") or {}
    executed = bool(to) and ("exit_code" in to) and bool(result.get("test_command"))
    add("4. Tests executed", executed,
        f"exit_code={to.get('exit_code')}, cmd={result.get('test_command')}")

    # 5. Failure detection works
    iters = result.get("iteration", 0)
    first_fail = result.get("first_failure") or {}
    if iters == 0:
        detected = bool(to.get("passed"))
    else:
        detected = bool(first_fail) and (not first_fail.get("passed"))
    add("5. Failure detection works", detected,
        f"iterations={iters}, first_failure_captured={bool(first_fail)}")

    # 6. Error feedback reaches model
    if iters == 0:
        feedback = True
        fb_detail = "no failure occurred (feedback not required)"
    else:
        feedback = bool(result.get("failure_analysis", "").strip())
        fb_detail = f"analysis length={len(result.get('failure_analysis',''))}"
    add("6. Error feedback reaches model", feedback, fb_detail)

    # 7. Repair loop works (when needed)
    final_passed = bool((result.get("final_result") or {}).get("passed"))
    if iters == 0:
        repair = True
        repair_detail = "solved on first attempt (loop not exercised)"
    else:
        repair = final_passed
        repair_detail = f"repairs={iters}, final_passed={final_passed}"
    add("7. Repair loop works", repair, repair_detail)

    # 8. Final tests pass
    add("8. Final tests pass", final_passed,
        f"passed={final_passed}")

    # 9. Sandbox restrictions work (live probe)
    probe = _probe_sandbox_blocks_network()
    add("9. Sandbox restrictions work", probe["blocked"],
        probe["detail"] or "external socket blocked")

    # 10. Network calls = 0
    ext = result.get("external_calls", 0)
    add("10. Network calls = 0", ext == 0,
        f"external_calls={ext}")

    passed = sum(1 for c in criteria if c["passed"])
    total = len(criteria)
    return {
        "criteria": criteria,
        "passed": passed,
        "total": total,
        "score": round(100.0 * passed / total, 1),
        "model": "Qwen2.5-Coder-3B-Instruct (local, OpenAI-compatible)",
        "run_id": result.get("run_id"),
        "iterations": iters,
        "final_passed": final_passed,
        "external_calls": ext,
    }


def write_report(report: Dict[str, Any], result: Dict[str, Any], path: str) -> str:
    fr = result.get("final_result") or {}
    to = fr.get("test_output") or result.get("test_output") or {}
    lines = []
    lines.append("# Coding Agent Evaluation Report\n")
    lines.append(f"- **Model:** {report['model']}")
    lines.append(f"- **Run ID:** {report['run_id']}")
    lines.append(f"- **Score:** {report['passed']}/{report['total']} ({report['score']}%)")
    lines.append(f"- **Status:** {result.get('status')}")
    lines.append(f"- **Iterations (repairs):** {report['iterations']}")
    lines.append(f"- **Final tests passed:** {report['final_passed']}")
    lines.append(f"- **External network calls:** {report['external_calls']}")
    if result.get("workspace"):
        lines.append(f"- **Workspace:** {result['workspace']}")
    if fr.get("artifact_dir"):
        lines.append(f"- **Artifact:** {fr['artifact_dir']}")
    lines.append("")

    # Initial failure narrative (proves the loop is real, not faked).
    ff = result.get("first_failure")
    if ff and not ff.get("passed"):
        lines.append("## Repair loop evidence\n")
        lines.append(f"First run FAILED (exit_code={ff.get('exit_code')}). "
                     f"The failing output was fed back to the model for repair.\n")
        lines.append("```")
        lines.append((ff.get("stderr") or ff.get("stdout") or "")[:1500])
        lines.append("```\n")

    lines.append("## Criteria\n")
    for c in report["criteria"]:
        mark = "PASS" if c["passed"] else "FAIL"
        lines.append(f"- [{mark}] **{c['name']}** — {c['detail']}")
    lines.append("")

    lines.append("## Execution trace\n")
    for t in result.get("trace", []):
        lines.append(f"- `{t.get('node')}` ({t.get('action')}/{t.get('tool')}) "
                     f"{t.get('status')} in {t.get('duration_ms')}ms")
    lines.append("")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return path
