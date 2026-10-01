"""Phase 18.3 — Backend API performance metrics tests."""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.client import ModelClient
from app.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_SLOW_TESTS"),
    reason="fast API unit tests run by default; integration tests need RUN_SLOW_TESTS=1",
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# General API
# ---------------------------------------------------------------------------
def test_general_run_returns_response_time_and_model_performance():
    with patch.object(ModelClient, 'generate_with_metrics', new_callable=AsyncMock, return_value={
        "content": "ANSWER",
        "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
        "performance": {"inference_seconds": 2.0, "tokens_per_second": 40.0, "prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
    }):
        resp = client.post("/api/general/run", json={"task": "What is 2+2?", "asset_tag": "", "use_rag": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["response_time_seconds"] is not None
    assert data["response_time_seconds"] > 0
    assert data["model_performance"] is not None
    assert data["model_performance"]["tokens_per_second"] == 40.0
    assert data["model_performance"]["inference_seconds"] == 2.0
    assert data["model_performance"]["completion_tokens"] == 80


def test_general_run_rag_returns_response_time():
    fake_hits = [
        {
            "source_file": "inspection_report.md",
            "document_type": "inspection_report",
            "score": 0.92,
            "text": "Catalyst hotspot detected.",
            "asset_tag": "R-1001",
            "chunk_id": "c1",
            "section": "findings",
            "retrieval_mode": "hybrid",
        }
    ]
    with patch("app.api.general.search_knowledge_base", return_value=fake_hits):
        with patch.object(ModelClient, 'generate_with_metrics', new_callable=AsyncMock, return_value={
            "content": "RAG ANSWER",
            "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
            "performance": {"inference_seconds": 1.5, "tokens_per_second": 66.67, "prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
        }):
            resp = client.post("/api/general/run", json={
                "task": "Give me information about the inspection report for R-1001.",
                "asset_tag": "R-1001",
                "use_rag": True,
            })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["rag_used"] is True
    assert data["response_time_seconds"] is not None
    assert data["response_time_seconds"] > 0
    assert data["model_performance"] is not None


# ---------------------------------------------------------------------------
# Coder API (mocked workflow)
# ---------------------------------------------------------------------------
def test_coder_run_returns_response_time():
    fake_result = {
        "run_id": "coder_test123",
        "status": "COMPLETED",
        "files": ["solution.py"],
        "file_contents": {"solution.py": "print('hello')"},
        "test_output": {"passed": True, "exit_code": 0},
        "test_command": "pytest",
        "iterations": 0,
        "failure_analysis": "",
        "workspace": "/tmp/coder_test123",
        "execution_trace": [],
        "errors": [],
        "external_calls": 0,
        "routing": {
            "selected_model": "qwen-coder",
            "task_type": "CODING",
            "all_local": True,
            "modality": "code",
            "models_required": ["qwen-coder"],
            "requires_rag": False,
            "requires_tools": False,
            "confidence": 1.0,
            "reason": "coding task",
            "capabilities": [],
            "local_only": True,
            "external_calls": 0,
        },
        "final_result": {},
        "model_performance": {
            "model_calls": 2,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "inference_seconds": 1.5,
            "tokens_per_second": 33.33,
        },
    }
    with patch("agent.coder.run.run_coder_task", return_value=fake_result):
        resp = client.post("/api/coder/run", json={"task": "Write hello world"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["response_time_seconds"] is not None
    assert data["response_time_seconds"] > 0
    assert data["model_performance"] is not None
    assert data["model_performance"]["tokens_per_second"] == 33.33


# ---------------------------------------------------------------------------
# Vision API
# ---------------------------------------------------------------------------
def test_vision_run_returns_response_time():
    fake_payload = {
        "result": {
            "description": "P&ID analysis",
            "findings": [],
            "entities": [],
            "confidence": 0.9,
            "model": "qwen-vision",
        },
        "external_calls": 0,
        "equipment_tags": ["P-1001"],
    }
    with patch("app.api.vision._analyze_guarded", return_value=fake_payload):
        resp = client.post("/api/vision/analyze", json={
            "file_path": "/tmp/test.jpg",
            "analysis_type": "general",
            "prompt": None,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["response_time_seconds"] is not None
    assert data["response_time_seconds"] > 0
    assert data["execution_time"] is not None
    assert data["model_performance"] is None


# ---------------------------------------------------------------------------
# Agent API
# ---------------------------------------------------------------------------
def test_agent_run_returns_response_time():
    fake_result = {
        "run_id": "run_test123",
        "status": "COMPLETED",
        "decision": "APPROVE",
        "reasoning_summary": "All checks passed.",
        "approval_required": False,
        "required_actions": [],
        "supporting_evidence": [],
        "findings": [],
        "artifacts": [],
        "evidence": [],
        "vision_evidence": [],
        "vision_tags": [],
        "calculations_summary": {},
        "verification": {},
        "trace": [],
        "errors": [],
        "image_path": None,
        "analysis_type": "general",
        "external_calls": 0,
        "routing": {
            "selected_model": "general",
            "task_type": "GENERAL_QA",
            "all_local": True,
            "modality": "text",
            "models_required": ["general"],
            "requires_rag": False,
            "requires_tools": False,
            "confidence": 1.0,
            "reason": "general task",
            "capabilities": [],
            "local_only": True,
            "external_calls": 0,
        },
    }
    with patch("agent.run.run_agent_task", return_value=fake_result):
        resp = client.post("/api/agent/run", json={"task": "Summarize this", "asset_tag": "R-1001"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["response_time_seconds"] is not None
    assert data["response_time_seconds"] > 0
    assert data["model_performance"] is None
