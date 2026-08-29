"""End-to-end agent test: full task, evaluation against ground truth, network sovereignty,
and FastAPI integration."""
import os
import socket
from pathlib import Path

import pytest

from agent.run import run_agent_task
from agent.evaluation import evaluate, write_report
from agent.security.netguard import no_network

TASK = (
    "Analyze the recent R-1001 operating data and inspection findings, compare them with "
    "the equipment manual and maintenance SOP, check the vendor recommendation, determine the "
    "required corrective action, and prepare a maintenance approval note."
)


def test_full_task_end_to_end():
    res = run_agent_task(TASK, asset_tag="R-1001", run_id="e2e_1", artifact_filename="R-1001_agent_test.docx")
    assert res["status"] == "VERIFIED"
    assert res["approval_required"] is True
    assert res["artifacts"], "artifact must be generated"
    assert os.path.exists(res["artifacts"][0])


def test_evaluation_against_ground_truth():
    res = run_agent_task(TASK, asset_tag="R-1001", run_id="e2e_eval", artifact_filename="R-1001_agent_test.docx")
    result = evaluate(res)
    assert result["passed"] == result["total"], [
        c for c in result["criteria"] if not c["pass"]
    ]
    assert result["score"] == 100.0
    assert result["findings_evidence_supported"] is True
    path = write_report(result, res)
    assert Path(path).exists()


def test_zero_external_network_calls():
    """The internal network guard must record zero external connections."""
    res = run_agent_task(TASK, asset_tag="R-1001", run_id="e2e_net", artifact_filename="R-1001_agent_test.docx")
    assert res["external_calls"] == 0


def test_netguard_blocks_external_connections():
    """Prove the guard actually blocks outbound sockets."""
    with no_network() as guard:
        with pytest.raises(Exception):
            # Attempt a real external connection (should be blocked).
            s = socket.create_connection(("8.8.8.8", 53), timeout=2)
            s.close()
    assert guard.external_calls >= 1


def test_agent_completes_under_netguard():
    """Running the whole agent while the guard is active must still succeed (no network used)."""
    with no_network() as guard:
        res = run_agent_task(TASK, asset_tag="R-1001", run_id="e2e_underguard", artifact_filename="R-1001_agent_test.docx")
    assert guard.external_calls == 0
    assert res["status"] == "VERIFIED"


def test_fastapi_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.agent import router

    app = FastAPI()
    app.include_router(router, prefix="/api/agent")

    client = TestClient(app)
    resp = client.post("/api/agent/run", json={"task": TASK, "asset_tag": "R-1001"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "VERIFIED"
    assert body["approval_required"] is True
    assert body["run_id"]
    assert body["artifacts"]

    # Fetch the stored run.
    got = client.get(f"/api/agent/runs/{body['run_id']}")
    assert got.status_code == 200
    assert got.json()["run_id"] == body["run_id"]
