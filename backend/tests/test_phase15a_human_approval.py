"""Phase 15A1 — Persistent Human Approval Gate Tests.

CPU ONLY. No GPU. No model server. No network.
"""
import hashlib
import multiprocessing
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from governance.approval import (
    ApprovalService,
    ApprovalStatus,
    ApprovalNotFoundError,
    ApprovalConflictError,
    ArtifactIntegrityError,
)

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


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
        "calculations_summary": {"sandbox_used": True},
        "verification": {"ok": True},
        "trace": [{"node": "make_decision"}],
        "errors": [],
        "image_path": None,
        "analysis_type": "general",
        "external_calls": 0,
        "routing": {"selected_model": "general", "task_type": "GENERAL_QA", "modality": "text"},
        "asset_identity": {"canonical_tag": "R-1001", "status": "VERIFIED"},
        "retrieval_summary": {"chunk_count": 1, "unique_asset_tags": ["R-1001"]},
        "output_dir": str(REPO / "data" / "outputs"),
        "asset_tag": "R-1001",
    }
    result.update(overrides)
    return result


class TestCreatePending:
    def test_create_valid_pending_approval(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_1", str(art))
        svc = _make_temp_service(tmp_path)
        record = svc.create_pending_from_run(result)
        assert record is not None
        assert record.status == ApprovalStatus.PENDING
        assert record.run_id == "run_1"
        assert record.artifact_path == str(art)
        expected_sha = hashlib.sha256(b"draft approval note").hexdigest()
        assert record.artifact_sha256 == expected_sha

    def test_approval_required_false_creates_no_record(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_2", str(art), approval_required=False)
        svc = _make_temp_service(tmp_path)
        record = svc.create_pending_from_run(result)
        assert record is None
        assert svc.list_pending() == []

    def test_missing_run_id_rejected(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("", str(art))
        svc = _make_temp_service(tmp_path)
        with pytest.raises(ApprovalConflictError):
            svc.create_pending_from_run(result)

    def test_empty_decision_rejected(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_3", str(art), decision="")
        svc = _make_temp_service(tmp_path)
        with pytest.raises(ApprovalConflictError):
            svc.create_pending_from_run(result)

    def test_missing_artifact_rejected(self, tmp_path: Path):
        result = _fake_run_result("run_4", str(tmp_path / "missing.docx"))
        svc = _make_temp_service(tmp_path)
        with pytest.raises(ApprovalConflictError):
            svc.create_pending_from_run(result)

    def test_verification_false_rejected(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_5", str(art), verification={"ok": False})
        svc = _make_temp_service(tmp_path)
        with pytest.raises(ApprovalConflictError):
            svc.create_pending_from_run(result)

    def test_artifact_outside_approved_root_rejected(self, tmp_path: Path):
        outside = Path(tempfile.gettempdir()) / "outside_approval.docx"
        _write_artifact(outside)
        result = _fake_run_result("run_6", str(outside))
        svc = _make_temp_service(tmp_path)
        with pytest.raises(ApprovalConflictError):
            svc.create_pending_from_run(result)

    def test_artifact_hash_stored_correctly(self, tmp_path: Path):
        content = b"known content for hash"
        art = _write_artifact(tmp_path / "art.docx", content)
        result = _fake_run_result("run_7", str(art))
        svc = _make_temp_service(tmp_path)
        record = svc.create_pending_from_run(result)
        assert record.artifact_sha256 == hashlib.sha256(content).hexdigest()

    def test_duplicate_same_run_id_idempotent(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_8", str(art))
        svc = _make_temp_service(tmp_path)
        r1 = svc.create_pending_from_run(result)
        r2 = svc.create_pending_from_run(result)
        assert r1.run_id == r2.run_id
        assert r1.artifact_sha256 == r2.artifact_sha256

    def test_duplicate_run_different_artifact_conflicts(self, tmp_path: Path):
        art1 = _write_artifact(tmp_path / "art1.docx", b"v1")
        art2 = _write_artifact(tmp_path / "art2.docx", b"v2")
        result1 = _fake_run_result("run_9", str(art1))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result1)
        result2 = _fake_run_result("run_9", str(art2))
        with pytest.raises(ApprovalConflictError):
            svc.create_pending_from_run(result2)


class TestStateTransitions:
    def test_pending_to_approved(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_10", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        record = svc.approve("run_10", "reviewer-a", "looks good")
        assert record.status == ApprovalStatus.APPROVED
        assert record.reviewer_id == "reviewer-a"
        assert record.reviewer_comment == "looks good"
        assert record.reviewed_at is not None
        assert record.reviewer_identity_verified == 0

    def test_pending_to_rejected(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_11", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        record = svc.reject("run_11", "reviewer-b", "bad data")
        assert record.status == ApprovalStatus.REJECTED
        assert record.reviewer_comment == "bad data"
        assert record.reviewer_identity_verified == 0

    def test_approved_to_rejected_blocked(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_12", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_12", "reviewer-a")
        with pytest.raises(ApprovalConflictError):
            svc.reject("run_12", "reviewer-b", "no")

    def test_rejected_to_approved_blocked(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_13", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.reject("run_13", "reviewer-b", "no")
        with pytest.raises(ApprovalConflictError):
            svc.approve("run_13", "reviewer-a")

    def test_approve_unknown_run_raises_not_found(self, tmp_path: Path):
        svc = _make_temp_service(tmp_path)
        with pytest.raises(ApprovalNotFoundError):
            svc.approve("run_unknown", "reviewer-a", "looks good")

    def test_reject_unknown_run_raises_not_found(self, tmp_path: Path):
        svc = _make_temp_service(tmp_path)
        with pytest.raises(ApprovalNotFoundError):
            svc.reject("run_unknown", "reviewer-b", "bad data")

    def test_get_unknown_run_raises_not_found(self, tmp_path: Path):
        svc = _make_temp_service(tmp_path)
        with pytest.raises(ApprovalNotFoundError):
            svc.get_record("run_unknown")

    def test_double_approve_blocked(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_14", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_14", "reviewer-a")
        with pytest.raises(ApprovalConflictError):
            svc.approve("run_14", "reviewer-a")

    def test_double_reject_blocked(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_15", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.reject("run_15", "reviewer-b", "no")
        with pytest.raises(ApprovalConflictError):
            svc.reject("run_15", "reviewer-b", "no")

    def test_missing_reviewer_blocked(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_16", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        with pytest.raises(ApprovalConflictError):
            svc.approve("run_16", "")

    def test_whitespace_reviewer_blocked(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_17", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        with pytest.raises(ApprovalConflictError):
            svc.approve("run_17", "   ")

    def test_reject_missing_comment_blocked(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_18", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        with pytest.raises(ApprovalConflictError):
            svc.reject("run_18", "reviewer-b", "")

    def test_reviewer_identity_verified_remains_false(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_19", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        rec = svc.approve("run_19", "reviewer-a")
        assert rec.reviewer_identity_verified == 0
        svc2 = _make_temp_service(tmp_path)
        result2 = _fake_run_result("run_19b", str(art))
        svc2.create_pending_from_run(result2)
        rec2 = svc2.reject("run_19b", "reviewer-b", "no")
        assert rec2.reviewer_identity_verified == 0


class TestRestartPersistence:
    def test_restart_pending(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_20", str(art))
        svc_a = _make_temp_service(tmp_path)
        svc_a.create_pending_from_run(result)
        svc_b = _make_temp_service(tmp_path)
        record = svc_b.get_record("run_20")
        assert record.status == ApprovalStatus.PENDING

    def test_restart_approved(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_21", str(art))
        svc_a = _make_temp_service(tmp_path)
        svc_a.create_pending_from_run(result)
        svc_a.approve("run_21", "reviewer-a")
        svc_b = _make_temp_service(tmp_path)
        record = svc_b.get_record("run_21")
        assert record.status == ApprovalStatus.APPROVED


class TestConcurrency:
    def test_concurrent_approve_reject_exactly_one_wins(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_22", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)

        results = {}

        def _approve():
            try:
                r = svc.approve("run_22", "reviewer-a")
                results["approve"] = r.status
            except ApprovalConflictError:
                results["approve"] = "conflict"

        def _reject():
            try:
                r = svc.reject("run_22", "reviewer-b", "no")
                results["reject"] = r.status
            except ApprovalConflictError:
                results["reject"] = "conflict"

        t1 = threading.Thread(target=_approve)
        t2 = threading.Thread(target=_reject)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        statuses = [v for v in results.values() if v != "conflict"]
        assert len(statuses) == 1
        assert statuses[0] in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)


class TestCrossProcessAtomicity:
    def test_cross_process_exactly_one_transition_wins(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_cross", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)

        db_path = str(tmp_path / "approvals.sqlite3")
        approved_roots = [
            str(tmp_path),
            str(REPO.parent / "data" / "outputs"),
            str(REPO.parent / "data" / "artifacts"),
        ]

        outcomes = _cross_process_race(
            db_path=db_path,
            approved_roots=approved_roots,
            run_id="run_cross",
        )

        successes = [o for o in outcomes if o[0] == "ok"]
        conflicts = [o for o in outcomes if o[0] == "conflict"]
        errors = [o for o in outcomes if o[0] == "error"]

        assert len(errors) == 0, f"unexpected errors: {errors}"
        assert len(successes) == 1, f"expected exactly 1 success, got {len(successes)}: {successes}"
        assert len(conflicts) == 1, f"expected exactly 1 conflict, got {len(conflicts)}: {conflicts}"

        svc_final = _make_temp_service(tmp_path)
        final = svc_final.get_record("run_cross")
        assert final.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)


def _cross_process_worker_approve(payload: dict):
    from governance.approval import ApprovalService, ApprovalConflictError, ApprovalNotFoundError

    svc = ApprovalService(
        db_path=payload["db_path"],
        approved_roots=payload["approved_roots"],
    )
    try:
        rec = svc.approve(payload["run_id"], payload["reviewer_id"], payload["comment"])
        return ("ok", rec.status)
    except (ApprovalConflictError, ApprovalNotFoundError):
        return ("conflict", None)
    except Exception as e:
        return ("error", str(e))


def _cross_process_worker_reject(payload: dict):
    from governance.approval import ApprovalService, ApprovalConflictError, ApprovalNotFoundError

    svc = ApprovalService(
        db_path=payload["db_path"],
        approved_roots=payload["approved_roots"],
    )
    try:
        rec = svc.reject(
            payload["run_id"], payload["reviewer_id"], payload["comment"]
        )
        return ("ok", rec.status)
    except (ApprovalConflictError, ApprovalNotFoundError):
        return ("conflict", None)
    except Exception as e:
        return ("error", str(e))


def _cross_process_race(*, db_path: str, approved_roots: list, run_id: str):
    payload = {
        "db_path": db_path,
        "approved_roots": approved_roots,
        "run_id": run_id,
        "reviewer_id": "reviewer-x",
        "comment": "race",
    }
    with multiprocessing.Pool(processes=2) as pool:
        outcomes = pool.map(
            _cross_process_worker_wrapper,
            [
                (_cross_process_worker_approve, payload),
                (_cross_process_worker_reject, payload),
            ],
        )
    return outcomes


def _cross_process_worker_wrapper(args):
    fn, payload = args
    return fn(payload)


class TestArtifactIntegrity:
    def test_artifact_tamper_blocks_approval(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx", b"original")
        result = _fake_run_result("run_23", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        Path(art).write_bytes(b"tampered")
        with pytest.raises(ArtifactIntegrityError):
            svc.approve("run_23", "reviewer-a")

    def test_artifact_tamper_blocks_rejection(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx", b"original")
        result = _fake_run_result("run_24", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        Path(art).write_bytes(b"tampered")
        with pytest.raises(ArtifactIntegrityError):
            svc.reject("run_24", "reviewer-b", "no")

    def test_approval_does_not_modify_artifact(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx", b"immutable")
        result = _fake_run_result("run_25", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        before = hashlib.sha256(Path(art).read_bytes()).hexdigest()
        svc.approve("run_25", "reviewer-a")
        after = hashlib.sha256(Path(art).read_bytes()).hexdigest()
        assert before == after


class TestSnapshot:
    def test_run_snapshot_excludes_raw_chunk_payload(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_26", str(art))
        result["retrieved_chunks"] = [{"text": "secret raw chunk"}]
        svc = _make_temp_service(tmp_path)
        record = svc.create_pending_from_run(result)
        snap = record.snapshot
        assert "retrieved_chunks" not in snap
        assert "retrieved_documents" not in snap

    def test_logical_artifact_path_does_not_leak_external_path(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_27", str(art))
        svc = _make_temp_service(tmp_path)
        record = svc.create_pending_from_run(result)
        # The service stores the absolute path under an approved root.
        assert str(tmp_path) in record.artifact_path


class TestApprovalAPI:
    def test_api_get_pending_returns_pending_only(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import approvals as approvals_router

        art1 = _write_artifact(tmp_path / "art1.docx")
        art2 = _write_artifact(tmp_path / "art2.docx")
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(_fake_run_result("run_28a", str(art1)))
        svc.create_pending_from_run(_fake_run_result("run_28b", str(art2)))
        svc.approve("run_28a", "reviewer-a")

        approvals_router._service = svc
        app = FastAPI()
        app.include_router(approvals_router.router, prefix="/api/approvals")
        client = TestClient(app)
        resp = client.get("/api/approvals/pending")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["run_id"] == "run_28b"

    def test_api_get_run_works(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import approvals as approvals_router

        art = _write_artifact(tmp_path / "art.docx")
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(_fake_run_result("run_29", str(art)))
        approvals_router._service = svc
        app = FastAPI()
        app.include_router(approvals_router.router, prefix="/api/approvals")
        client = TestClient(app)
        resp = client.get("/api/approvals/run_29")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == "run_29"

    def test_api_unknown_run_404(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import approvals as approvals_router

        svc = _make_temp_service(tmp_path)
        approvals_router._service = svc
        app = FastAPI()
        app.include_router(approvals_router.router, prefix="/api/approvals")
        client = TestClient(app)
        resp = client.get("/api/approvals/unknown_run")
        assert resp.status_code == 404

    def test_api_approve_unknown_run_404(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import approvals as approvals_router

        svc = _make_temp_service(tmp_path)
        approvals_router._service = svc
        app = FastAPI()
        app.include_router(approvals_router.router, prefix="/api/approvals")
        client = TestClient(app)
        resp = client.post(
            "/api/approvals/unknown_run/approve",
            json={"reviewer_id": "maintenance-lead", "comment": "approved"},
        )
        assert resp.status_code == 404

    def test_api_reject_unknown_run_404(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import approvals as approvals_router

        svc = _make_temp_service(tmp_path)
        approvals_router._service = svc
        app = FastAPI()
        app.include_router(approvals_router.router, prefix="/api/approvals")
        client = TestClient(app)
        resp = client.post(
            "/api/approvals/unknown_run/reject",
            json={"reviewer_id": "maintenance-lead", "comment": "bad data"},
        )
        assert resp.status_code == 404

    def test_api_approve_works(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import approvals as approvals_router

        art = _write_artifact(tmp_path / "art.docx")
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(_fake_run_result("run_30", str(art)))
        approvals_router._service = svc
        app = FastAPI()
        app.include_router(approvals_router.router, prefix="/api/approvals")
        client = TestClient(app)
        resp = client.post(
            "/api/approvals/run_30/approve",
            json={"reviewer_id": "maintenance-lead", "comment": "approved"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "APPROVED"

    def test_api_reject_works(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import approvals as approvals_router

        art = _write_artifact(tmp_path / "art.docx")
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(_fake_run_result("run_31", str(art)))
        approvals_router._service = svc
        app = FastAPI()
        app.include_router(approvals_router.router, prefix="/api/approvals")
        client = TestClient(app)
        resp = client.post(
            "/api/approvals/run_31/reject",
            json={"reviewer_id": "maintenance-lead", "comment": "bad data"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"

    def test_api_invalid_transition_409(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import approvals as approvals_router

        art = _write_artifact(tmp_path / "art.docx")
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(_fake_run_result("run_32", str(art)))
        svc.approve("run_32", "reviewer-a")
        approvals_router._service = svc
        app = FastAPI()
        app.include_router(approvals_router.router, prefix="/api/approvals")
        client = TestClient(app)
        resp = client.post(
            "/api/approvals/run_32/reject",
            json={"reviewer_id": "reviewer-b", "comment": "no"},
        )
        assert resp.status_code == 409

    def test_api_logical_artifact_path_is_repo_relative(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import approvals as approvals_router

        repo_out = REPO.parent / "data" / "outputs" / "art.docx"
        art = _write_artifact(repo_out)
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(_fake_run_result("run_37", str(art)))
        approvals_router._service = svc
        app = FastAPI()
        app.include_router(approvals_router.router, prefix="/api/approvals")
        client = TestClient(app)
        resp = client.get("/api/approvals/run_37")
        assert resp.status_code == 200
        body = resp.json()
        path = body["artifact_path"]
        assert ".." not in path
        assert not os.path.isabs(path)


class TestAgentIntegration:
    def test_agent_integration_creates_pending_only(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import agent as agent_router
        from app.api import approvals as approvals_router

        svc = _make_temp_service(tmp_path)
        approvals_router._service = svc

        original_service = agent_router.ApprovalService
        agent_router.ApprovalService = lambda: svc
        try:
            app = FastAPI()
            app.include_router(agent_router.router, prefix="/api/agent")
            client = TestClient(app)
            resp = client.post(
                "/api/agent/run",
                json={
                    "task": (
                        "Analyze the recent R-1001 operating data and inspection findings, "
                        "compare them with the equipment manual and maintenance SOP, "
                        "check the vendor recommendation, determine the required corrective "
                        "action, and prepare a maintenance approval note."
                    ),
                    "asset_tag": "R-1001",
                },
            )
        finally:
            agent_router.ApprovalService = original_service

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["approval_required"] is True
        assert body["human_review_status"] == "PENDING"
        assert body["approval_record_available"] is True
        run_id = body["run_id"]
        record = svc.get_record(run_id)
        assert record.status == ApprovalStatus.PENDING

    def test_non_approval_agent_result_not_required(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import agent as agent_router
        from app.api import approvals as approvals_router

        svc = _make_temp_service(tmp_path)
        approvals_router._service = svc

        fake_result = {
            "run_id": "run_no_approval",
            "status": "VERIFIED",
            "decision": "No action needed.",
            "reasoning_summary": "none",
            "approval_required": False,
            "required_actions": [],
            "supporting_evidence": [],
            "findings": [],
            "artifacts": [],
            "evidence": [],
            "vision_evidence": [],
            "vision_tags": [],
            "calculations_summary": {},
            "verification": {"ok": True},
            "trace": [],
            "errors": [],
            "image_path": None,
            "analysis_type": "general",
            "external_calls": 0,
            "routing": {"selected_model": "general", "task_type": "GENERAL_QA", "modality": "text"},
            "asset_identity": {"canonical_tag": "R-1001", "status": "VERIFIED"},
            "retrieval_summary": {"chunk_count": 0, "unique_asset_tags": []},
            "output_dir": str(REPO.parent / "data" / "outputs"),
            "asset_tag": "R-1001",
        }
        with patch("agent.run.run_agent_task", return_value=fake_result):
            app = FastAPI()
            app.include_router(agent_router.router, prefix="/api/agent")
            client = TestClient(app)
            resp = client.post(
                "/api/agent/run",
                json={"task": "Say hello.", "asset_tag": "R-1001"},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["approval_required"] is False
        assert body["human_review_status"] == "NOT_REQUIRED"
        assert body["approval_record_available"] is False
        assert svc.list_pending() == []

    def test_no_automatic_approval(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import agent as agent_router
        from app.api import approvals as approvals_router

        art = _write_artifact(tmp_path / "art.docx")
        svc = _make_temp_service(tmp_path)
        approvals_router._service = svc

        fake_result = _fake_run_result("run_auto", str(art))
        original_service = agent_router.ApprovalService
        agent_router.ApprovalService = lambda: svc
        try:
            with patch("agent.run.run_agent_task", return_value=fake_result):
                app = FastAPI()
                app.include_router(agent_router.router, prefix="/api/agent")
                client = TestClient(app)
                resp = client.post(
                    "/api/agent/run",
                    json={"task": "shutdown required", "asset_tag": "R-1001"},
                )
        finally:
            agent_router.ApprovalService = original_service

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["approval_required"] is True
        assert body["human_review_status"] == "PENDING"
        assert body["approval_record_available"] is True
        record = svc.get_record("run_auto")
        assert record.status == ApprovalStatus.PENDING
