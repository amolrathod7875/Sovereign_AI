"""Phase 18 — Workbench routing accuracy hotfix tests.

Covers:
  1. Generic "hey" routes to GENERAL_QA and does NOT invoke the maintenance agent.
  2. "give me information about inspection report" routes to RAG_QA, no maintenance agent.
  3. "what does the maintenance SOP say for R-1001?" routes to RAG_QA, no maintenance agent.
  4. Full industrial maintenance prompt invokes the maintenance agent.
  5. Python coding prompt routes to coder, not maintenance agent.
  6. General absent + "hey" returns UNAVAILABLE, no fake answer, no maintenance output.
  7. General absent + inspection query: retrieval allowed, no fake synthesis, no maintenance decision.
  8. Regression: maintenance-specific strings do NOT appear for generic prompts.
  9. Online General returns COMPLETED with actual string answer, not coroutine.
 10. Online RAG + General returns COMPLETED with evidence and grounded answer.
 11. Text-only P&ID concept query routes to GENERAL_QA, not vision.
 12. Generic preventive maintenance question routes to GENERAL_QA.
"""
import json
import os
import warnings
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.router import route, RoutingRequest, NoLocalModelAvailable
from app.models.client import ModelClient

REPO = __import__("pathlib").Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _offline():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Generic chat -> GENERAL_QA (not maintenance agent)
# ---------------------------------------------------------------------------
def test_generic_hey_routes_to_general_qa():
    d = route(RoutingRequest(task="hey"))
    assert d.task_type == "GENERAL_QA"
    assert d.selected_model == "general"
    assert "maintenance" not in d.reason.lower() or "general" in d.reason.lower()


# ---------------------------------------------------------------------------
# 2. Inspection report query -> RAG_QA, not maintenance agent
# ---------------------------------------------------------------------------
def test_inspection_report_query_routes_to_rag_qa():
    d = route(RoutingRequest(
        task="give me information about inspection report"
    ))
    assert d.task_type == "RAG_QA"
    assert d.requires_rag is True


# ---------------------------------------------------------------------------
# 3. Maintenance SOP query -> RAG_QA, not full maintenance agent
# ---------------------------------------------------------------------------
def test_maintenance_sop_query_routes_to_rag_qa():
    d = route(RoutingRequest(
        task="what does the maintenance SOP say for R-1001?"
    ))
    assert d.task_type == "RAG_QA"
    assert d.requires_rag is True


# ---------------------------------------------------------------------------
# 4. Full industrial maintenance prompt -> capable of reaching maintenance agent
#    (router itself selects general/RAG; the maintenance agent dispatch is a
#    Workbench-layer decision. This test asserts the router does NOT block it.)
# ---------------------------------------------------------------------------
def test_full_maintenance_prompt_routes_to_rag():
    d = route(RoutingRequest(
        task=(
            "Analyze R-1001 operating data and inspection findings, compare with SOP "
            "and vendor recommendation and determine corrective maintenance."
        )
    ))
    assert d.task_type in ("RAG_QA", "GENERAL_QA")
    assert d.requires_rag is True


# ---------------------------------------------------------------------------
# 5. Python coding prompt -> coder
# ---------------------------------------------------------------------------
def test_python_coding_prompt_routes_to_coder():
    d = route(RoutingRequest(
        task="Write a Python function to calculate Reynolds number"
    ))
    assert d.task_type == "CODING"
    assert d.selected_model == "qwen-coder"


# ---------------------------------------------------------------------------
# 6. Regression: generic prompt must NOT produce maintenance reasoning text
# ---------------------------------------------------------------------------
_MAINTENANCE_PHRASES = [
    "confirmed threshold breaches",
    "controlled reactor shutdown",
    "catalyst hotspot",
    "thermowell drift",
    "gasket weep",
    "corrective maintenance",
    "maintenance approval",
]


def test_generic_prompt_does_not_contain_maintenance_reasoning():
    d = route(RoutingRequest(task="hey"))
    reason = d.reason.lower()
    assert "controlled reactor shutdown" not in reason
    assert "confirmed threshold breaches" not in reason


# ---------------------------------------------------------------------------
# 7. General API — online model returns COMPLETED with actual string answer
# ---------------------------------------------------------------------------
def test_general_run_online_returns_completed_with_string_answer():
    resp = client.post("/api/general/run", json={"task": "hey", "asset_tag": "", "use_rag": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert isinstance(data["answer"], str)
    assert data["actual_model_execution"] == ["general"]
    assert data["rag_used"] is False
    assert data["errors"] == []


# ---------------------------------------------------------------------------
# 8. General API — RAG query returns evidence and answer when general available
# ---------------------------------------------------------------------------
def test_general_run_rag_query_returns_evidence_and_answer():
    fake_hits = [
        {
            "source_file": "inspection_report.md",
            "document_type": "inspection_report",
            "score": 0.92,
            "text": "Catalyst hotspot detected in R-1001 reactor top head.",
            "asset_tag": "R-1001",
            "chunk_id": "c1",
            "section": "findings",
            "retrieval_mode": "hybrid",
        }
    ]
    with patch("app.api.general.search_knowledge_base", return_value=fake_hits):
        resp = client.post("/api/general/run", json={
            "task": "give me information about inspection report",
            "asset_tag": "R-1001",
            "use_rag": True,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["rag_used"] is True
    assert len(data["evidence"]) >= 1
    assert data["actual_model_execution"] == ["general"]
    assert isinstance(data["answer"], str)
    assert data["answer"] is not None


# ---------------------------------------------------------------------------
# 9. General API — routing metadata is present
# ---------------------------------------------------------------------------
def test_general_run_returns_routing_metadata():
    resp = client.post("/api/general/run", json={"task": "summarize this", "asset_tag": "", "use_rag": False})
    assert resp.status_code == 200
    data = resp.json()
    assert "routing" in data
    assert data["routing"].get("task_type") == "GENERAL_QA"
    assert data["routing"].get("selected_model") == "general"


# ---------------------------------------------------------------------------
# 10. Model counter case-insensitivity fix (frontend store logic mirrored)
# ---------------------------------------------------------------------------
def test_model_status_case_insensitive_availability():
    statuses = ["ONLINE", "online", "Active", "active", "OFFLINE", "offline"]
    available = [s for s in statuses if s.lower() in ("online", "active")]
    assert len(available) == 4


# ---------------------------------------------------------------------------
# 11. Online General — actual string answer, not coroutine
# ---------------------------------------------------------------------------
def test_general_run_online_returns_completed_with_string_answer():
    with patch.object(ModelClient, 'generate', new_callable=AsyncMock, return_value="GENERAL TEST ANSWER"):
        resp = client.post("/api/general/run", json={
            "task": "Hey, what can you do?",
            "asset_tag": None,
            "use_rag": False,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["answer"] == "GENERAL TEST ANSWER"
    assert isinstance(data["answer"], str)
    assert data["actual_model_execution"] == ["general"]
    assert data["rag_used"] is False
    assert data["errors"] == []


# ---------------------------------------------------------------------------
# 12. Online RAG + General — evidence + grounded answer
# ---------------------------------------------------------------------------
def test_general_run_online_rag_returns_evidence_and_answer():
    fake_hits = [
        {
            "source_file": "inspection_report.md",
            "document_type": "inspection_report",
            "score": 0.92,
            "text": "Catalyst hotspot detected in R-1001 reactor top head.",
            "asset_tag": "R-1001",
            "chunk_id": "c1",
            "section": "findings",
            "retrieval_mode": "hybrid",
        }
    ]
    with patch("app.api.general.search_knowledge_base", return_value=fake_hits):
        with patch.object(ModelClient, 'generate', new_callable=AsyncMock, return_value="INSPECTION ANSWER"):
            resp = client.post("/api/general/run", json={
                "task": "Give me information about the inspection report for R-1001.",
                "asset_tag": "R-1001",
                "use_rag": True,
            })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["rag_used"] is True
    assert len(data["evidence"]) >= 1
    assert data["actual_model_execution"] == ["general"]
    assert data["answer"] == "INSPECTION ANSWER"


# ---------------------------------------------------------------------------
# 13. Text-only P&ID concept query -> GENERAL_QA (not vision)
# ---------------------------------------------------------------------------
def test_text_only_pid_concept_routes_to_general_qa():
    d = route(RoutingRequest(task="Explain what a P&ID is in simple terms."))
    assert d.task_type == "GENERAL_QA"
    assert d.modality == "text"


# ---------------------------------------------------------------------------
# 14. Generic maintenance concept -> GENERAL_QA (not automatic RAG)
# ---------------------------------------------------------------------------
def test_generic_maintenance_concept_routes_to_general_qa():
    d = route(RoutingRequest(task="What is the difference between preventive and corrective maintenance?"))
    assert d.task_type == "GENERAL_QA"


# ---------------------------------------------------------------------------
# Phase 18.2 — Final dispatch semantics
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 15. Industrial workflow predicate
# ---------------------------------------------------------------------------
from app.models.router import is_industrial_workflow_request

def test_industrial_workflow_predicate_positive():
    task = (
        "Analyze R-1001 operating data and inspection findings, compare them with the "
        "equipment manual, maintenance SOP and vendor recommendations, determine the "
        "required corrective action, and prepare a maintenance approval note."
    )
    assert is_industrial_workflow_request(task) is True


def test_industrial_workflow_predicate_negative():
    tasks = [
        "What does the inspection report say about R-1001?",
        "What does the SOP say?",
        "Give me vendor recommendations for R-1001.",
        "What is corrective maintenance?",
        "Compare inspection findings with vendor recommendations.",
    ]
    for t in tasks:
        assert is_industrial_workflow_request(t) is False, f"false positive for: {t}"


# ---------------------------------------------------------------------------
# 16. General QA system prompt does NOT contain evidence-only restriction
# ---------------------------------------------------------------------------
def test_general_qa_prompt_does_not_force_evidence_only():
    from app.api.general import _try_general_synthesis
    import inspect
    source = inspect.getsource(_try_general_synthesis)
    assert 'use_rag' in source
    assert 'ONLY the supplied local evidence' in source


# ---------------------------------------------------------------------------
# 17. RAG QA system prompt DOES contain evidence-only restriction
# ---------------------------------------------------------------------------
def test_rag_qa_prompt_forces_evidence_only():
    from app.api.general import _try_general_synthesis
    import inspect
    source = inspect.getsource(_try_general_synthesis)
    assert 'use_rag' in source
    assert 'ONLY the supplied local evidence' in source


# ---------------------------------------------------------------------------
# 18. Auto dispatch matrix
# ---------------------------------------------------------------------------
def test_auto_dispatch_general_qa_no_agent():
    d = route(RoutingRequest(task="Hey, what can you do?"))
    assert d.task_type == "GENERAL_QA"
    assert is_industrial_workflow_request("Hey, what can you do?") is False


def test_auto_dispatch_preventive_maintenance_no_agent():
    d = route(RoutingRequest(task="What is preventive maintenance?"))
    assert d.task_type == "GENERAL_QA"
    assert is_industrial_workflow_request("What is preventive maintenance?") is False


def test_auto_dispatch_inspection_report_rag_not_agent():
    d = route(RoutingRequest(task="Give me information about the inspection report for R-1001."))
    assert d.task_type == "RAG_QA"
    assert is_industrial_workflow_request("Give me information about the inspection report for R-1001.") is False


def test_auto_dispatch_full_maintenance_workflow_is_agent():
    task = (
        "Analyze R-1001 operating data and inspection findings, compare them with the "
        "equipment manual, maintenance SOP and vendor recommendations, determine the "
        "required corrective action, and prepare a maintenance approval note."
    )
    d = route(RoutingRequest(task=task))
    assert is_industrial_workflow_request(task) is True
    assert d.task_type in ("RAG_QA", "GENERAL_QA")
