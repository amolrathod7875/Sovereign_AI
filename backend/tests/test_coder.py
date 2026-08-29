"""Integration test for the local coding agent.

Skipped automatically when the local Qwen Coder server is not reachable, so the
suite stays green in CI without a model. Run the server (see run_coder_e2e.py)
to exercise the full repair loop.
"""
import os
import sys
import urllib.request
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent.coder.config import CODER_ENDPOINT
from agent.coder.evaluation import evaluate


def _server_up() -> bool:
    url = CODER_ENDPOINT.rstrip("/") + "/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=3):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _server_up(), reason="local Qwen Coder server not running")


DEMO_TASK = (
    "Write a Python program that reads a CSV containing sensor readings with "
    "timestamp, temperature, pressure, and vibration columns. Detect values "
    "exceeding configurable thresholds and output a summary containing the number "
    "of breaches and the first breach timestamp for each signal."
)


def test_coder_pipeline_end_to_end():
    from agent.coder.run import run_coder_task

    result = run_coder_task(DEMO_TASK)
    assert result["status"] == "COMPLETED", result.get("errors")
    assert result["external_calls"] == 0

    report = evaluate(result)
    assert report["passed"] == report["total"], report["criteria"]
    assert report["external_calls"] == 0
