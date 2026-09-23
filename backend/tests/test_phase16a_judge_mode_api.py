"""Phase 16A1 — Judge Mode Backend API Tests.

CPU ONLY. No GPU. No model servers. No external network.
"""
import json
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from judge.service import JudgeService, COMMITTED_HISTORICAL_EVIDENCE, FROZEN_EVALUATION_SNAPSHOT, LIVE, LIVE_PERSISTENT, UNAVAILABLE
from app.api import judge as judge_router
from app.schemas import ComponentStatus, SystemStatus
from governance.approval import ApprovalService, ApprovalStatus


def _write_artifact(path: Path, content: bytes = b"draft approval note") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path)


def _fake_run_result(run_id: str, artifact_path: str, **overrides) -> dict:
    result = {
        "run_id": run_id,
        "status": "VERIFIED",
        "decision": "Initiate shutdown.",
        "reasoning_summary": "sensor breaches.",
        "approval_required": True,
        "required_actions": ["shutdown"],
        "supporting_evidence": ["sensor_dataset"],
        "findings": [],
        "artifacts": [artifact_path],
        "evidence": [],
        "vision_evidence": [],
        "vision_tags": [],
        "calculations_summary": {"sandbox_used": True, "any_threshold_breach": True, "breached_signals": ["TI-1001"], "inspection_findings": ["catalyst_hotspot"], "vendor_parts": ["HRS-CAT-22"], "sop_requirements": ["controlled shutdown"]},
        "verification": {"ok": True},
        "trace": [{"node": "make_decision"}],
        "errors": [],
        "image_path": None,
        "analysis_type": "general",
        "external_calls": 0,
        "routing": {"selected_model": "general", "task_type": "GENERAL_QA", "modality": "text", "models_required": ["general"], "requires_rag": False, "requires_tools": False, "local_only": True, "all_local": True, "confidence": 0.9, "reason": "text task"},
        "asset_identity": {"canonical_tag": "R-1001", "status": "VERIFIED"},
        "retrieval_summary": {"chunk_count": 1, "unique_asset_tags": ["R-1001"], "source_files": ["inspection_report.pdf"], "document_types": ["inspection_report"], "retrieval_modes": ["hybrid"]},
        "output_dir": str(REPO / "data" / "outputs"),
        "asset_tag": "R-1001",
    }
    result.update(overrides)
    return result


def _make_temp_service(tmp_path: Path, **kwargs):
    db_path = str(tmp_path / "approvals.sqlite3")
    roots = kwargs.pop("approved_roots", [])
    roots.extend([
        str(tmp_path),
        str(REPO.parent / "data" / "outputs"),
        str(REPO.parent / "data" / "artifacts"),
    ])
    roots = sorted(set(roots))
    return ApprovalService(db_path=db_path, approved_roots=roots, **kwargs)


def _create_pending(tmp_path: Path, run_id: str):
    art = _write_artifact(tmp_path / f"{run_id}.docx")
    svc = _make_temp_service(tmp_path)
    result = _fake_run_result(run_id, str(art))
    svc.create_pending_from_run(result)
    return svc, str(art)


def _approve_run(svc, run_id: str):
    svc.approve(run_id, "reviewer-a", "looks good")


def _reject_run(svc, run_id: str):
    svc.reject(run_id, "reviewer-b", "bad data")


def _mock_system_status(monkeypatch, components):
    async def _mock():
        return SystemStatus(
            sovereign=True,
            gpu=None,
            services={},
            components=components,
            uptime_seconds=100,
            external_api_calls=0,
            blocked_connections=0,
        )
    monkeypatch.setattr("app.api.system.get_system_status", _mock, raising=False)


def _make_client(tmp_path, monkeypatch, components=None):
    if components is None:
        components = [ComponentStatus(id="general", name="General Model", status="UNAVAILABLE", detail="no server", endpoint="http://localhost:8001/v1", local=True)]
    _mock_system_status(monkeypatch, components)

    monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")

    app = FastAPI()
    app.include_router(judge_router.router, prefix="/api/judge")
    return TestClient(app)


class TestJudgeOverview:
    def test_overview_returns_200(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200

    def test_overview_source_types_explicit(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["runtime"]["source_type"] == LIVE
        assert body["governance"]["source_type"] == LIVE_PERSISTENT
        assert body["claim_boundaries"]["reviewer_identity_authenticated"] is False

    def test_overview_repository_commit_safe(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["repository"]["commit"] == "abc123"

    def test_overview_empty_governance_db(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["governance"]["pending_review_count"] == 0
        assert body["governance"]["chain"]["entry_count"] == 0
        assert body["governance"]["chain"]["valid"] is True
        assert body["governance"]["chain"]["status"] == "VALID"
        assert body["latest_terminal_run"] is None

    def test_overview_pending_count_correct(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_p1")
        _create_pending(tmp_path, "run_p2")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["governance"]["pending_review_count"] == 2
        assert len(body["governance"]["pending_reviews"]) == 2

    def test_overview_latest_terminal_derived_from_chain_head(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_t1")
        _approve_run(svc, "run_t1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["governance"]["chain"]["head_run_id"] == "run_t1"
        assert body["latest_terminal_run"] is not None
        assert body["latest_terminal_run"]["run_id"] == "run_t1"

    def test_overview_chain_validity_surfaced(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_v1")
        _approve_run(svc, "run_v1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["governance"]["chain"]["valid"] is True
        assert body["governance"]["chain"]["status"] == "VALID"

    def test_overview_invalid_chain_surfaced_without_500(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_c1")
        _approve_run(svc, "run_c1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE receipt_chain SET chain_sha256 = 'bad_hash' WHERE run_id = 'run_c1'")
        conn.commit()
        conn.close()
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["governance"]["chain"]["valid"] is False
        assert body["governance"]["chain"]["status"] == "INVALID"

    def test_overview_reviewer_authenticated_false(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        body = resp.json()
        assert body["claim_boundaries"]["reviewer_identity_authenticated"] is False

    def test_overview_whole_machine_certification_false(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        body = resp.json()
        assert body["claim_boundaries"]["whole_machine_airgap_certified"] is False

    def test_overview_tamper_proof_false(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        body = resp.json()
        assert body["claim_boundaries"]["receipt_chain_tamper_proof"] is False

    def test_overview_external_anchor_false(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        body = resp.json()
        assert body["claim_boundaries"]["external_trust_anchor_present"] is False

    def test_overview_digital_signature_false(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        body = resp.json()
        assert body["claim_boundaries"]["digital_signature_present"] is False

    def test_overview_general_runtime_derived_from_live(self, tmp_path, monkeypatch):
        components = [ComponentStatus(id="general", name="General Model", status="ONLINE", detail="test")]
        client = _make_client(tmp_path, monkeypatch, components=components)
        resp = client.get("/api/judge/overview")
        body = resp.json()
        assert body["claim_boundaries"]["general_runtime_status"] == "ONLINE"

    def test_overview_200_when_flagship_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("judge.service.FLAGSHIP_REPORT", tmp_path / "nonexistent.json")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200

    def test_overview_200_when_evaluation_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", tmp_path / "nonexistent.json")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200


class TestJudgeRunDetail:
    def test_unknown_run_returns_404(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_unknown")
        assert resp.status_code == 404

    def test_pending_run_returns_200(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_pending_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_pending_1")
        assert resp.status_code == 200

    def test_pending_receipt_unavailable(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_pending_2")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_pending_2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["receipt"]["available"] is False

    def test_pending_chain_unlinked(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_pending_3")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_pending_3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["chain"]["linked"] is False

    def test_approved_run_receipt_available(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_approved_1")
        _approve_run(svc, "run_approved_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_approved_1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["receipt"]["available"] is True
        assert body["receipt"]["receipt_id"] == "receipt:run_approved_1"

    def test_approved_run_chain_linked(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_approved_2")
        _approve_run(svc, "run_approved_2")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_approved_2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["chain"]["linked"] is True
        assert body["chain"]["sequence_no"] == 1

    def test_rejected_run_supported(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_rejected_1")
        _reject_run(svc, "run_rejected_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_rejected_1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["approval_status"] == "REJECTED"
        assert body["receipt"]["available"] is True
        assert body["chain"]["linked"] is True

    def test_reviewer_identity_verified_remains_false(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_rev_1")
        _approve_run(svc, "run_rev_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_rev_1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["human_review"]["reviewer_identity_verified"] is False

    def test_artifact_logical_path_only(self, tmp_path, monkeypatch):
        repo_out = REPO.parent / "data" / "outputs" / "art_logic.docx"
        art = _write_artifact(repo_out)
        svc = _make_temp_service(tmp_path)
        result = _fake_run_result("run_art_1", str(art))
        svc.create_pending_from_run(result)
        _approve_run(svc, "run_art_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_art_1")
        assert resp.status_code == 200
        body = resp.json()
        path = body["artifact"]["logical_path"]
        assert ".." not in path
        assert not os.path.isabs(path)

    def test_retrieval_summary_present(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_ret_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_ret_1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["retrieval"]["chunk_count"] == 1
        assert body["retrieval"]["source_files"] == ["inspection_report.pdf"]

    def test_no_raw_chunks(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_chunks_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_chunks_1")
        assert resp.status_code == 200
        text = resp.text
        assert "secret raw chunk" not in text

    def test_calculations_compact(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_calc_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_calc_1")
        assert resp.status_code == 200
        body = resp.json()
        assert "any_threshold_breach" in body["calculations"]
        assert "breached_signals" in body["calculations"]
        assert "sandbox_used" in body["calculations"]

    def test_executed_nodes_sanitized(self, tmp_path, monkeypatch):
        art = _write_artifact(tmp_path / "run_trace_1.docx")
        result = _fake_run_result("run_trace_1", str(art), trace=[
            {"node": "agent_step", "internal_stack": "secret_stack_trace", "reasoning": "hidden_chain_of_thought"},
            {"name": "tool_call", "confidence": 0.9},
        ])
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        _approve_run(svc, "run_trace_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_trace_1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["execution_trace"]["executed_nodes"] == ["agent_step", "tool_call"]
        assert "secret_stack_trace" not in resp.text
        assert "hidden_chain_of_thought" not in resp.text

    def test_routing_present(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_route_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_route_1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["routing"]["selected_model"] == "general"
        assert body["routing"]["task_type"] == "GENERAL_QA"

    def test_routing_not_equal_to_execution(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_rx_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_rx_1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["routing"]["selected_model"] == "general"
        assert body["actual_model_execution"]["recorded_models"] == []
        assert body["actual_model_execution"]["status"] == "NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE"

    def test_text_only_no_model_evidence_empty_recorded_models(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_txt_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_txt_1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["actual_model_execution"]["recorded_models"] == []
        assert body["actual_model_execution"]["status"] == "NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE"

    def test_terminal_receipt_verification_surfaced(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_ver_1")
        _approve_run(svc, "run_ver_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_ver_1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["receipt"]["available"] is True
        assert "checks" in body["receipt"]
        assert "valid" in body["receipt"]

    def test_global_chain_verification_surfaced(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_chain_1")
        _approve_run(svc, "run_chain_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_chain_1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["chain"]["global_chain_valid"] is True
        assert body["chain"]["global_chain_status"] == "VALID"
        assert body["chain"]["linked"] is True

    def test_run_detail_no_absolute_paths(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_path_1")
        _approve_run(svc, "run_path_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_path_1")
        text = resp.text
        assert "D:\\Sovereign_AI" not in text
        assert "C:\\Users\\shiva" not in text


class TestJudgeFlagship:
    def _make_flagship(self, tmp_path, data):
        path = tmp_path / "flagship.json"
        path.write_text(json.dumps(data))
        return path

    def test_flagship_source_type_historical(self, tmp_path, monkeypatch):
        flagship_data = {
            "timestamp": "2026-09-22T15:32:44Z",
            "run_id": "run_07d24d69e01e",
            "status": "VERIFIED",
            "asset_identity": {"canonical_tag": "R-1001", "status": "VERIFIED"},
            "retrieval_summary": {"chunk_count": 36, "retrieval_modes": ["hybrid"]},
            "calculations_summary": {"sandbox_used": True},
            "decision": "shutdown",
            "approval_required": True,
            "artifacts": ["data/outputs/R-1001.docx"],
            "verification": {"ok": True},
            "external_calls": 0,
            "flagship_validation": {
                "checks": {f"check_{i}": True for i in range(14)}
            },
        }
        path = self._make_flagship(tmp_path, flagship_data)
        monkeypatch.setattr("judge.service.FLAGSHIP_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/flagship")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source_type"] == COMMITTED_HISTORICAL_EVIDENCE

    def test_flagship_report_timestamp_surfaced(self, tmp_path, monkeypatch):
        flagship_data = {
            "timestamp": "2026-09-22T15:32:44Z",
            "run_id": "run_07d24d69e01e",
            "status": "VERIFIED",
            "asset_identity": {"canonical_tag": "R-1001", "status": "VERIFIED"},
            "retrieval_summary": {"chunk_count": 36, "retrieval_modes": ["hybrid"]},
            "calculations_summary": {"sandbox_used": True},
            "decision": "shutdown",
            "approval_required": True,
            "artifacts": ["data/outputs/R-1001.docx"],
            "verification": {"ok": True},
            "external_calls": 0,
            "flagship_validation": {"checks": {f"check_{i}": True for i in range(14)}},
        }
        path = self._make_flagship(tmp_path, flagship_data)
        monkeypatch.setattr("judge.service.FLAGSHIP_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/flagship")
        body = resp.json()
        assert body["timestamp"] == "2026-09-22T15:32:44Z"

    def test_flagship_14_14_computed_dynamically(self, tmp_path, monkeypatch):
        flagship_data = {
            "timestamp": "2026-09-22T15:32:44Z",
            "run_id": "run_07d24d69e01e",
            "status": "VERIFIED",
            "asset_identity": {"canonical_tag": "R-1001", "status": "VERIFIED"},
            "retrieval_summary": {"chunk_count": 36, "retrieval_modes": ["hybrid"]},
            "calculations_summary": {"sandbox_used": True},
            "decision": "shutdown",
            "approval_required": True,
            "artifacts": ["data/outputs/R-1001.docx"],
            "verification": {"ok": True},
            "external_calls": 0,
            "flagship_validation": {"checks": {f"check_{i}": True for i in range(14)}},
        }
        path = self._make_flagship(tmp_path, flagship_data)
        monkeypatch.setattr("judge.service.FLAGSHIP_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/flagship")
        body = resp.json()
        assert body["validation_checks_total"] == 14
        assert body["validation_checks_passed"] == 14
        assert body["failed_checks"] == []

    def test_flagship_artifact_absolute_path_not_leaked(self, tmp_path, monkeypatch):
        flagship_data = {
            "timestamp": "2026-09-22T15:32:44Z",
            "run_id": "run_07d24d69e01e",
            "status": "VERIFIED",
            "asset_identity": {"canonical_tag": "R-1001", "status": "VERIFIED"},
            "retrieval_summary": {"chunk_count": 36, "retrieval_modes": ["hybrid"]},
            "calculations_summary": {"sandbox_used": True},
            "decision": "shutdown",
            "approval_required": True,
            "artifacts": ["D:\\Sovereign_AI\\data\\outputs\\R-1001.docx"],
            "verification": {"ok": True},
            "external_calls": 0,
            "flagship_validation": {"checks": {f"check_{i}": True for i in range(14)}},
        }
        path = self._make_flagship(tmp_path, flagship_data)
        monkeypatch.setattr("judge.service.FLAGSHIP_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/flagship")
        assert resp.status_code == 200
        assert "D:\\Sovereign_AI" not in resp.text

    def test_flagship_external_calls_from_evidence(self, tmp_path, monkeypatch):
        flagship_data = {
            "timestamp": "2026-09-22T15:32:44Z",
            "run_id": "run_07d24d69e01e",
            "status": "VERIFIED",
            "asset_identity": {"canonical_tag": "R-1001", "status": "VERIFIED"},
            "retrieval_summary": {"chunk_count": 36, "retrieval_modes": ["hybrid"]},
            "calculations_summary": {"sandbox_used": True},
            "decision": "shutdown",
            "approval_required": True,
            "artifacts": ["data/outputs/R-1001.docx"],
            "verification": {"ok": True},
            "external_calls": 0,
            "flagship_validation": {"checks": {f"check_{i}": True for i in range(14)}},
        }
        path = self._make_flagship(tmp_path, flagship_data)
        monkeypatch.setattr("judge.service.FLAGSHIP_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/flagship")
        body = resp.json()
        assert body["external_calls"] == 0

    def test_missing_flagship_report_handled(self, tmp_path, monkeypatch):
        monkeypatch.setattr("judge.service.FLAGSHIP_REPORT", tmp_path / "nonexistent.json")
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/flagship")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["source_type"] == UNAVAILABLE
        assert "reason" in body

    def test_malformed_flagship_report_handled(self, tmp_path, monkeypatch):
        path = tmp_path / "bad_flagship.json"
        path.write_text("not json")
        monkeypatch.setattr("judge.service.FLAGSHIP_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/flagship")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["source_type"] == UNAVAILABLE

    def test_no_model_name_invented_if_absent(self, tmp_path, monkeypatch):
        flagship_data = {
            "timestamp": "2026-09-22T15:32:44Z",
            "run_id": "run_07d24d69e01e",
            "status": "VERIFIED",
            "asset_identity": {"canonical_tag": "R-1001", "status": "VERIFIED"},
            "retrieval_summary": {"chunk_count": 36, "retrieval_modes": ["hybrid"]},
            "calculations_summary": {"sandbox_used": True},
            "decision": "shutdown",
            "approval_required": True,
            "artifacts": ["data/outputs/R-1001.docx"],
            "verification": {"ok": True},
            "external_calls": 0,
            "flagship_validation": {"checks": {f"check_{i}": True for i in range(14)}},
        }
        path = self._make_flagship(tmp_path, flagship_data)
        monkeypatch.setattr("judge.service.FLAGSHIP_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/flagship")
        body = resp.json()
        assert "selected_model" not in body
        assert "models_required" not in body


class TestJudgeEvaluation:
    def _make_scorecard(self, tmp_path, data):
        path = tmp_path / "scorecard.json"
        path.write_text(json.dumps(data))
        return path

    def test_evaluation_marked_frozen_historical_snapshot(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10, "metrics": {"general_model_runtime_status": "UNAVAILABLE"}},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        assert resp.status_code == 200
        body = resp.json()
        assert body["historical_snapshot"] is True
        assert body["source_type"] == FROZEN_EVALUATION_SNAPSHOT

    def test_evaluation_generated_at_surfaced(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert body["generated_at"] == "2026-09-23T01:58:46Z"

    def test_evaluation_source_commit_surfaced(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert body["source_repository_commit"] == "b2ce3cc"

    def test_evaluation_rag_hit_at_1_source_value(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert body["rag"]["hit_at_1"] == 2

    def test_evaluation_rag_hit_at_3_source_value(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert body["rag"]["hit_at_3"] == 4

    def test_evaluation_rag_hit_at_5_source_value(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert body["rag"]["hit_at_5"] == 6

    def test_evaluation_mrr_source_value(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert body["rag"]["mrr"] == 0.5556

    def test_evaluation_identity_count_source(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert body["asset_identity"]["passed"] == 18
        assert body["asset_identity"]["total"] == 18

    def test_evaluation_routing_count_source(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert body["routing"]["passed"] == 10
        assert body["routing"]["total"] == 10

    def test_evaluation_security_count_source(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert body["sovereignty_security"]["passed"] == 12
        assert body["sovereignty_security"]["total"] == 12

    def test_evaluation_flagship_uses_14_check_metrics(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert body["flagship"]["checks_passed"] == 14
        assert body["flagship"]["checks_total"] == 14

    def test_evaluation_no_composite_score(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert "overall_score" not in body
        assert "competition_score" not in body
        assert "ranking" not in body

    def test_evaluation_regression_labeled_historical(self, tmp_path, monkeypatch):
        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "b2ce3cc",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = self._make_scorecard(tmp_path, scorecard_data)
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "b2ce3cc")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        body = resp.json()
        assert body["regression_snapshot"]["historical_snapshot"] is True

    def test_missing_scorecard_handled(self, tmp_path, monkeypatch):
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", tmp_path / "nonexistent.json")
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["source_type"] == UNAVAILABLE
        assert "reason" in body

    def test_malformed_scorecard_handled(self, tmp_path, monkeypatch):
        path = tmp_path / "bad_scorecard.json"
        path.write_text("not json")
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/evaluation")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["source_type"] == UNAVAILABLE


class TestJudgePrivacy:
    def test_no_absolute_paths_in_overview(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        text = resp.text
        assert "D:\\Sovereign_AI" not in text
        assert "C:\\Users\\shiva" not in text

    def test_no_absolute_paths_in_run_detail(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_priv_1")
        _approve_run(svc, "run_priv_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_priv_1")
        text = resp.text
        assert "D:\\Sovereign_AI" not in text
        assert "C:\\Users\\shiva" not in text

    def test_no_raw_snapshot_json_leaked(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_priv_2")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_priv_2")
        body = resp.json()
        assert "run_snapshot_json" not in body
        assert "snapshot" not in body

    def test_no_high_dim_data_in_response(self, tmp_path, monkeypatch):
        _create_pending(tmp_path, "run_priv_3")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_priv_3")
        body = resp.json()
        assert "embedding" not in json.dumps(body).lower()
        assert "vector" not in json.dumps(body).lower()

    def test_no_credentials_in_overview(self, tmp_path, monkeypatch):
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/overview")
        text = resp.text
        assert "api_key" not in text.lower()
        assert "password" not in text.lower()
        assert "secret" not in text.lower()


class TestJudgeLiveVsHistorical:
    def test_live_general_online_historical_unauthorized(self, tmp_path, monkeypatch):
        components = [ComponentStatus(id="general", name="General Model", status="ONLINE", detail="test")]
        _mock_system_status(monkeypatch, components)

        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "old_commit",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10, "metrics": {"general_model_runtime_status": "UNAVAILABLE"}},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = tmp_path / "scorecard.json"
        path.write_text(json.dumps(scorecard_data))
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")

        client = _make_client(tmp_path, monkeypatch, components=components)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["runtime"]["components"]
        general_component = [c for c in body["runtime"]["components"] if c["id"] == "general"][0]
        assert general_component["status"] == "ONLINE"
        assert body["evaluation"]["routing"]["metrics"]["general_model_runtime_status"] == "UNAVAILABLE"

    def test_live_general_unavailable_historical_unchanged(self, tmp_path, monkeypatch):
        components = [ComponentStatus(id="general", name="General Model", status="UNAVAILABLE", detail="test")]
        _mock_system_status(monkeypatch, components)

        scorecard_data = {
            "generated_at": "2026-09-23T01:58:46Z",
            "repository_commit": "old_commit",
            "categories": {
                "industrial_golden": {"passed": 10, "total": 10},
                "rag_retrieval": {"passed": 6, "total": 6, "metrics": {"queries_total": 6, "hit_at_1": 2, "hit_at_3": 4, "hit_at_5": 6, "mrr": 0.5556, "primary_source_at_1": 2, "provenance_complete_hits": 30, "total_hits": 30, "foreign_asset_hits": 0}},
                "asset_identity": {"passed": 18, "total": 18},
                "routing": {"passed": 10, "total": 10, "metrics": {"general_model_runtime_status": "ONLINE"}},
                "runtime_resilience": {"passed": 14, "total": 14},
                "sovereignty_security": {"passed": 12, "total": 12},
                "artifact_sandbox": {"passed": 11, "total": 11},
                "flagship_live": {"metrics": {"flagship_checks_passed": 14, "flagship_checks_total": 14}},
                "regression": {"passed": 304, "failed": 2, "total": 320, "metrics": {"passed": 304, "failed": 2, "skipped": 14}},
            },
        }
        path = tmp_path / "scorecard.json"
        path.write_text(json.dumps(scorecard_data))
        monkeypatch.setattr("judge.service.SCORECARD_REPORT", path)
        monkeypatch.setattr("judge.service._git_rev_parse_head", lambda: "abc123")

        client = _make_client(tmp_path, monkeypatch, components=components)
        resp = client.get("/api/judge/overview")
        assert resp.status_code == 200
        body = resp.json()
        general_component = [c for c in body["runtime"]["components"] if c["id"] == "general"][0]
        assert general_component["status"] == "UNAVAILABLE"
        assert body["evaluation"]["routing"]["metrics"]["general_model_runtime_status"] == "ONLINE"


class TestJudgeRoutingExecution:
    def test_routing_selected_model_not_equal_to_execution(self, tmp_path, monkeypatch):
        svc, art = _create_pending(tmp_path, "run_routing_1")
        _approve_run(svc, "run_routing_1")
        db_path = str(tmp_path / "approvals.sqlite3")
        monkeypatch.setenv("SOVEREIGN_APPROVAL_DB", db_path)
        client = _make_client(tmp_path, monkeypatch)
        resp = client.get("/api/judge/runs/run_routing_1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["routing"]["selected_model"] == "general"
        assert body["actual_model_execution"]["recorded_models"] == []
        assert body["actual_model_execution"]["status"] == "NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE"
