"""Phase 5A end-to-end run for the local coding agent.

Runs the coding workflow on the deterministic sensor-CSV demo task, evaluates the
10-point checklist, and writes reports/coder_evaluation.md.

Requires the local Qwen Coder server to be running, e.g.:
  python scripts/serve_model.py --model-id qwen-coder \
      --model-path models/qwen-coder/qwen2.5-coder-3b-instruct-q4_k_m.gguf \
      --port 8002 --n-ctx 8192
"""
import json
import logging
import os
import sys
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from agent.coder.run import run_coder_task
from agent.coder.config import CODER_ENDPOINT
from agent.coder.evaluation import evaluate, write_report

DEMO_TASK = (
    "Write a Python program that reads a CSV containing sensor readings with "
    "timestamp, temperature, pressure, and vibration columns. Detect values "
    "exceeding configurable thresholds and output a summary containing the number "
    "of breaches and the first breach timestamp for each signal."
)

REPORT_PATH = os.path.join(BACKEND, "..", "reports", "coder_evaluation.md")


def _server_up() -> bool:
    base = CODER_ENDPOINT
    url = base.rstrip("/") + "/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=3):
            return True
    except Exception:
        return False


def main():
    if not _server_up():
        sys.exit(
            "ERROR: local Qwen Coder server not reachable at "
            f"{CODER_ENDPOINT}.\nStart it with:\n"
            "  python scripts/serve_model.py --model-id qwen-coder "
            "--model-path models/qwen-coder/qwen2.5-coder-3b-instruct-q4_k_m.gguf "
            "--port 8002 --n-ctx 8192"
        )

    result = run_coder_task(DEMO_TASK)
    print("\n===== CODER RUN =====")
    print("run_id:", result["run_id"])
    print("status:", result["status"])
    print("iterations:", result["iteration"])
    print("external_calls:", result["external_calls"])
    print("files:", result["files"])
    print("trace_nodes:", [t.get("node") for t in result.get("trace", [])])
    if result.get("first_failure"):
        ff = result["first_failure"]
        print("\n===== FIRST FAILURE (repair-loop evidence) =====")
        print("exit_code:", ff.get("exit_code"))
        print((ff.get("stdout") or "")[:600])
        print((ff.get("stderr") or "")[:600])

    report = evaluate(result)
    path = write_report(report, result, REPORT_PATH)
    print("\n===== EVALUATION =====")
    print(f"score: {report['passed']}/{report['total']} ({report['score']}%)")
    print(f"model: {report['model']}")
    print(f"external_calls: {report['external_calls']}")
    print("report:", os.path.abspath(path))
    print(json.dumps(report["criteria"], indent=2))

    assert result["external_calls"] == 0, "network sovereignty violated"
    assert report["passed"] == report["total"], "evaluation failed"
    assert result["status"] == "COMPLETED", result["status"]
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
