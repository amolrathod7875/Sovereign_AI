"""Phase 15B1 — Sovereignty Receipt Tests.

CPU ONLY. No GPU. No model server. No network.
"""
import hashlib
import json
import multiprocessing
import os
import sys
from pathlib import Path

import pytest

from governance.approval import (
    ApprovalService,
    ApprovalStatus,
    ApprovalConflictError,
    ApprovalNotFoundError,
    ArtifactIntegrityError,
)
from governance.receipt import (
    ReceiptService,
    ReceiptRecord,
    ReceiptNotFoundError,
    ReceiptNotReadyError,
    ReceiptConflictError,
    ReceiptIntegrityError,
    _canonicalize,
    _compute_receipt_sha256,
    _build_receipt_id,
    _safe_trace_nodes,
    _vision_models_from_evidence,
    build_receipt_payload,
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


def _make_temp_receipt_service(tmp_path: Path, **kwargs):
    db_path = str(tmp_path / "approvals.sqlite3")
    return ReceiptService(db_path=db_path, **kwargs)


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


class TestReceiptNotReady:
    def test_pending_approval_has_no_receipt(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_101", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        receipt_svc = _make_temp_receipt_service(tmp_path)
        with pytest.raises(ReceiptNotFoundError):
            receipt_svc.get_receipt("run_101")

    def test_get_receipt_for_pending_raises_not_ready(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_102", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        receipt_svc = _make_temp_receipt_service(tmp_path)
        with pytest.raises((ReceiptNotFoundError, ReceiptNotReadyError)):
            receipt_svc.get_receipt("run_102")


class TestReceiptCreation:
    def test_approve_creates_receipt(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_103", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        record = svc.approve("run_103", "reviewer-a", "looks good")
        assert record.status == ApprovalStatus.APPROVED
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_103")
        assert receipt.receipt_id == _build_receipt_id("run_103")
        assert receipt.schema_version == "1.0"
        assert receipt.approval_status == "APPROVED"

    def test_reject_creates_receipt(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_104", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        record = svc.reject("run_104", "reviewer-b", "bad data")
        assert record.status == ApprovalStatus.REJECTED
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_104")
        assert receipt.receipt_id == _build_receipt_id("run_104")
        assert receipt.schema_version == "1.0"
        assert receipt.approval_status == "REJECTED"


class TestReceiptUniqueness:
    def test_exactly_one_receipt_per_run(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_105", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_105", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        r1 = receipt_svc.get_receipt("run_105")
        assert r1.receipt_id == _build_receipt_id("run_105")
        with pytest.raises(ReceiptConflictError):
            receipt_svc._insert(
                receipt_svc._connect(),
                run_id="run_105",
                receipt_id=_build_receipt_id("run_105b"),
                schema_version="1.0",
                created_at="2024-01-01T00:00:00+00:00",
                approval_status="APPROVED",
                artifact_sha256="abc",
                payload={},
                receipt_sha256="def",
            )


class TestReceiptPersistence:
    def test_receipt_survives_service_restart(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_106", str(art))
        svc_a = _make_temp_service(tmp_path)
        svc_a.create_pending_from_run(result)
        svc_a.approve("run_106", "reviewer-a", "ok")
        svc_b = _make_temp_service(tmp_path)
        receipt_svc_b = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc_b.get_receipt("run_106")
        assert receipt.approval_status == "APPROVED"
        assert receipt.receipt_id == _build_receipt_id("run_106")

    def test_approval_and_receipt_use_same_sqlite_db(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_107", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_107", "reviewer-a", "ok")
        db_path = str(tmp_path / "approvals.sqlite3")
        receipt_svc = ReceiptService(db_path=db_path)
        receipt = receipt_svc.get_receipt("run_107")
        assert receipt.approval_status == "APPROVED"


class TestReceiptDeterminism:
    def test_schema_version_is_1_0(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_108", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_108", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_108")
        assert receipt.schema_version == "1.0"

    def test_canonical_json_deterministic(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_109", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_109", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_109")
        payload = receipt.payload
        canonical1 = _canonicalize(payload)
        payload2 = dict(reversed(list(payload.items())))
        canonical2 = _canonicalize(payload2)
        assert canonical1 == canonical2
        assert _compute_receipt_sha256(payload) == receipt.receipt_sha256

    def test_different_dict_insertion_order_same_hash(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_110", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_110", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_110")
        payload = receipt.payload
        payload_reordered = dict(sorted(payload.items(), key=lambda kv: kv[0], reverse=True))
        assert _compute_receipt_sha256(payload) == _compute_receipt_sha256(payload_reordered)

    def test_receipt_sha256_matches_canonical_payload(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_111", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_111", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_111")
        assert _compute_receipt_sha256(receipt.payload) == receipt.receipt_sha256

    def test_run_id_included_correctly(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_112", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_112", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_112")
        assert receipt.payload["run_id"] == "run_112"
        assert receipt.payload["receipt_id"] == _build_receipt_id("run_112")

    def test_build_receipt_id_deterministic(self):
        assert _build_receipt_id("run_x") == "receipt:run_x"
        assert _build_receipt_id("run_y") == "receipt:run_y"


class TestReceiptPayload:
    def test_asset_identity_included(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_113", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_113", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_113")
        asset = receipt.payload["asset"]
        assert asset["requested_tag"] == "R-1001"
        assert asset["canonical_tag"] == "R-1001"
        assert asset["identity_status"] == "VERIFIED"

    def test_decision_included(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_114", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_114", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_114")
        ai = receipt.payload["ai_recommendation"]
        assert ai["decision"] == "Initiate shutdown."
        assert ai["approval_required"] is True

    def test_approval_required_true(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_115", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_115", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_115")
        assert receipt.payload["ai_recommendation"]["approval_required"] is True

    def test_approved_human_status(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_116", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_116", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_116")
        assert receipt.payload["human_review"]["status"] == "APPROVED"

    def test_rejected_human_status(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_117", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.reject("run_117", "reviewer-b", "bad")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_117")
        assert receipt.payload["human_review"]["status"] == "REJECTED"

    def test_reviewer_id_correct(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_118", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_118", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_118")
        assert receipt.payload["human_review"]["reviewer_id"] == "reviewer-a"

    def test_reviewer_identity_verified_remains_false(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_119", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_119", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_119")
        assert receipt.payload["human_review"]["reviewer_identity_verified"] is False

    def test_artifact_sha_matches_approval(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_120", str(art))
        svc = _make_temp_service(tmp_path)
        rec = svc.create_pending_from_run(result)
        svc.approve("run_120", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_120")
        assert receipt.payload["artifact"]["sha256"] == rec.artifact_sha256
        assert receipt.artifact_sha256 == rec.artifact_sha256

    def test_artifact_path_logical_not_absolute(self, tmp_path: Path):
        repo_out = REPO.parent / "data" / "outputs" / "art.docx"
        art = _write_artifact(repo_out)
        result = _fake_run_result("run_121", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_121", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_121")
        logical_path = receipt.payload["artifact"]["logical_path"]
        assert ".." not in logical_path
        assert not Path(logical_path).is_absolute()

    def test_verification_ok_represented(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_122", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_122", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_122")
        assert receipt.payload["artifact"]["verification_ok"] is True

    def test_retrieval_summary_represented(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_123", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_123", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_123")
        retrieval = receipt.payload["retrieval"]
        assert retrieval["chunk_count"] == 1
        assert retrieval["unique_asset_tags"] == ["R-1001"]

    def test_raw_chunk_text_absent(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_124", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_124", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_124")
        payload_str = json.dumps(receipt.payload)
        assert "retrieved_chunks" not in payload_str
        assert "raw chunk text" not in payload_str.lower()

    def test_raw_image_bytes_absent(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_125", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_125", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_125")
        payload_str = json.dumps(receipt.payload)
        assert "PNG" not in payload_str.upper()
        assert "JPEG" not in payload_str.upper()

    def test_trace_converted_to_executed_nodes(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_126", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_126", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_126")
        nodes = receipt.payload["execution"]["executed_nodes"]
        assert "make_decision" in nodes

    def test_sandbox_used_accurate(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_127", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_127", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_127")
        assert receipt.payload["execution"]["sandbox_used"] is True

    def test_routing_metadata_represented(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_128", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_128", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_128")
        routing = receipt.payload["routing"]
        assert routing["selected_model"] == "general"
        assert routing["task_type"] == "GENERAL_QA"

    def test_routing_model_not_counted_as_executed(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_129", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_129", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_129")
        model_exec = receipt.payload["model_execution"]
        assert "general" not in model_exec["recorded_models"]
        assert model_exec["status"] == "NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE"

    def test_explicit_vision_evidence_model_recorded(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result(
            "run_130",
            str(art),
            vision_evidence=[{"model": "llama-3-vision", "frames": 1}],
        )
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_130", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_130")
        model_exec = receipt.payload["model_execution"]
        assert "llama-3-vision" in model_exec["recorded_models"]
        assert model_exec["status"] == "EXPLICIT_VISION_EVIDENCE"

    def test_no_explicit_execution_evidence_returns_empty(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_131", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_131", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_131")
        model_exec = receipt.payload["model_execution"]
        assert model_exec["recorded_models"] == []
        assert model_exec["status"] == "NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE"

    def test_external_calls_0_represented(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_132", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_132", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_132")
        sov = receipt.payload["sovereignty"]
        assert sov["external_calls_recorded"] == 0

    def test_whole_machine_airgap_false(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_133", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_133", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_133")
        sov = receipt.payload["sovereignty"]
        assert sov["whole_machine_airgap_certified"] is False

    def test_network_guard_scope_recorded(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_134", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_134", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_134")
        sov = receipt.payload["sovereignty"]
        assert sov["network_guard_scope"] == "application-level agent run"


class TestReceiptVerification:
    def test_verify_valid_receipt(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_135", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_135", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        result = receipt_svc.verify_receipt("run_135")
        assert result["valid"] is True

    def test_verify_payload_tamper_invalid(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_136", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_136", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_136")
        payload = dict(receipt.payload)
        payload["asset"]["requested_tag"] = "TAMPERED"
        conn = receipt_svc._connect()
        try:
            conn.execute(
                "UPDATE sovereignty_receipts SET payload_json = ? WHERE run_id = ?",
                (json.dumps(payload, default=str), "run_136"),
            )
        finally:
            conn.close()
        result = receipt_svc.verify_receipt("run_136")
        assert result["valid"] is False

    def test_verify_hash_tamper_invalid(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_137", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_137", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        conn = receipt_svc._connect()
        try:
            conn.execute(
                "UPDATE sovereignty_receipts SET receipt_sha256 = ? WHERE run_id = ?",
                ("badhash", "run_137"),
            )
        finally:
            conn.close()
        result = receipt_svc.verify_receipt("run_137")
        assert result["valid"] is False

    def test_verify_artifact_after_approval_tamper_invalid(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx", b"original")
        result = _fake_run_result("run_138", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_138", "reviewer-a", "ok")
        Path(art).write_bytes(b"tampered")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        result = receipt_svc.verify_receipt("run_138")
        assert result["valid"] is False

    def test_verify_approval_record_mismatch_invalid(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_139", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_139", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_139")
        payload = dict(receipt.payload)
        payload["human_review"]["reviewer_id"] = "other-reviewer"
        conn = receipt_svc._connect()
        try:
            conn.execute(
                "UPDATE sovereignty_receipts SET payload_json = ?, receipt_sha256 = ? WHERE run_id = ?",
                (json.dumps(payload, default=str), _compute_receipt_sha256(payload), "run_139"),
            )
        finally:
            conn.close()
        result = receipt_svc.verify_receipt("run_139")
        assert result["valid"] is False

    def test_verify_reviewer_mismatch_invalid(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_140", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_140", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        conn = receipt_svc._connect()
        try:
            conn.execute(
                "UPDATE sovereignty_receipts SET payload_json = ?, receipt_sha256 = ? WHERE run_id = ?",
                (
                    json.dumps({"human_review": {"reviewer_id": "wrong"}}, default=str),
                    _compute_receipt_sha256({"human_review": {"reviewer_id": "wrong"}}),
                    "run_140",
                ),
            )
        finally:
            conn.close()
        result = receipt_svc.verify_receipt("run_140")
        assert result["valid"] is False


class TestReceiptAPI:
    def test_api_get_pending_receipt_409(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipts as receipts_router

        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_141", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipts_router._service = receipt_svc
        app = FastAPI()
        app.include_router(receipts_router.router, prefix="/api/receipts")
        client = TestClient(app)
        resp = client.get("/api/receipts/run_141")
        assert resp.status_code == 409

    def test_api_get_unknown_receipt_404(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipts as receipts_router

        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipts_router._service = receipt_svc
        app = FastAPI()
        app.include_router(receipts_router.router, prefix="/api/receipts")
        client = TestClient(app)
        resp = client.get("/api/receipts/run_unknown")
        assert resp.status_code == 404

    def test_api_get_approved_receipt_200(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipts as receipts_router

        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_142", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_142", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipts_router._service = receipt_svc
        app = FastAPI()
        app.include_router(receipts_router.router, prefix="/api/receipts")
        client = TestClient(app)
        resp = client.get("/api/receipts/run_142")
        assert resp.status_code == 200
        assert resp.json()["approval_status"] == "APPROVED"

    def test_api_get_rejected_receipt_200(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipts as receipts_router

        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_143", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.reject("run_143", "reviewer-b", "bad")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipts_router._service = receipt_svc
        app = FastAPI()
        app.include_router(receipts_router.router, prefix="/api/receipts")
        client = TestClient(app)
        resp = client.get("/api/receipts/run_143")
        assert resp.status_code == 200
        assert resp.json()["approval_status"] == "REJECTED"

    def test_api_verify_valid_receipt(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipts as receipts_router

        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_144", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_144", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipts_router._service = receipt_svc
        app = FastAPI()
        app.include_router(receipts_router.router, prefix="/api/receipts")
        client = TestClient(app)
        resp = client.get("/api/receipts/run_144/verify")
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_api_verify_tampered_receipt(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipts as receipts_router

        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_145", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_145", "reviewer-a", "ok")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_145")
        payload = dict(receipt.payload)
        payload["asset"]["requested_tag"] = "TAMPERED"
        conn = receipt_svc._connect()
        try:
            conn.execute(
                "UPDATE sovereignty_receipts SET payload_json = ? WHERE run_id = ?",
                (json.dumps(payload, default=str), "run_145"),
            )
        finally:
            conn.close()
        receipts_router._service = receipt_svc
        app = FastAPI()
        app.include_router(receipts_router.router, prefix="/api/receipts")
        client = TestClient(app)
        resp = client.get("/api/receipts/run_145/verify")
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_approval_response_surfaces_receipt_metadata(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import approvals as approvals_router

        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_146", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        approvals_router._service = svc
        app = FastAPI()
        app.include_router(approvals_router.router, prefix="/api/approvals")
        client = TestClient(app)
        resp = client.post(
            "/api/approvals/run_146/approve",
            json={"reviewer_id": "reviewer-a", "comment": "ok"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["receipt_available"] is True
        assert "receipt_id" in body
        assert "receipt_sha256" in body

    def test_pending_approval_response_receipt_unavailable(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import approvals as approvals_router

        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_147", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        approvals_router._service = svc
        app = FastAPI()
        app.include_router(approvals_router.router, prefix="/api/approvals")
        client = TestClient(app)
        resp = client.get("/api/approvals/run_147")
        assert resp.status_code == 200
        body = resp.json()
        assert body["receipt_available"] is False

    def test_no_receipt_update_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipts as receipts_router

        app = FastAPI()
        app.include_router(receipts_router.router, prefix="/api/receipts")
        client = TestClient(app)
        resp = client.put("/api/receipts/run_x")
        assert resp.status_code == 405

    def test_no_receipt_delete_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipts as receipts_router

        app = FastAPI()
        app.include_router(receipts_router.router, prefix="/api/receipts")
        client = TestClient(app)
        resp = client.delete("/api/receipts/run_x")
        assert resp.status_code == 405


class TestAtomicRollback:
    def test_approve_failure_leaves_pending_and_no_receipt(self, tmp_path: Path):
        from unittest.mock import patch

        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_148", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)

        def failing_insert(conn, **kwargs):
            raise RuntimeError("receipt insertion failure")

        with patch.object(ReceiptService, "_insert", new=failing_insert):
            with pytest.raises(ApprovalConflictError):
                svc.approve("run_148", "reviewer-a", "ok")

        record = svc.get_record("run_148")
        assert record.status == ApprovalStatus.PENDING
        assert record.reviewer_id is None
        assert record.reviewed_at is None
        receipt_svc = _make_temp_receipt_service(tmp_path)
        with pytest.raises(ReceiptNotFoundError):
            receipt_svc.get_receipt("run_148")

    def test_reject_failure_leaves_pending_and_no_receipt(self, tmp_path: Path):
        from unittest.mock import patch

        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_149", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)

        def failing_insert(conn, **kwargs):
            raise RuntimeError("receipt insertion failure")

        with patch.object(ReceiptService, "_insert", new=failing_insert):
            with pytest.raises(ApprovalConflictError):
                svc.reject("run_149", "reviewer-b", "bad")

        record = svc.get_record("run_149")
        assert record.status == ApprovalStatus.PENDING
        assert record.reviewer_id is None
        assert record.reviewed_at is None
        receipt_svc = _make_temp_receipt_service(tmp_path)
        with pytest.raises(ReceiptNotFoundError):
            receipt_svc.get_receipt("run_149")

    def test_approve_with_unreadable_artifact_rolls_back(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_150", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        Path(art).write_bytes(b"")
        os.chmod(str(art), 0o000)
        try:
            with pytest.raises((ArtifactIntegrityError, PermissionError)):
                svc.approve("run_150", "reviewer-a", "ok")
        finally:
            try:
                os.chmod(str(art), 0o644)
            except Exception:
                pass
        record = svc.get_record("run_150")
        assert record.status == ApprovalStatus.PENDING


class TestCrossProcessReceiptRace:
    def test_cross_process_exactly_one_receipt(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art.docx")
        result = _fake_run_result("run_cross_r", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)

        db_path = str(tmp_path / "approvals.sqlite3")
        approved_roots = [
            str(tmp_path),
            str(REPO.parent / "data" / "outputs"),
            str(REPO.parent / "data" / "artifacts"),
        ]

        outcomes = _cross_process_receipt_race(
            db_path=db_path,
            approved_roots=approved_roots,
            run_id="run_cross_r",
        )

        successes = [o for o in outcomes if o[0] == "ok"]
        conflicts = [o for o in outcomes if o[0] == "conflict"]
        errors = [o for o in outcomes if o[0] == "error"]

        assert len(errors) == 0, f"unexpected errors: {errors}"
        assert len(successes) == 1, f"expected exactly 1 success, got {len(successes)}: {successes}"
        assert len(conflicts) == 1, f"expected exactly 1 conflict, got {len(conflicts)}: {conflicts}"

        svc_final = _make_temp_service(tmp_path)
        final = svc_final.get_record("run_cross_r")
        assert final.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)

        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_cross_r")
        assert receipt.approval_status == final.status
        assert receipt.receipt_id == _build_receipt_id("run_cross_r")


def _cross_process_worker_approve_receipt(payload: dict):
    from governance.approval import ApprovalService, ApprovalConflictError

    svc = ApprovalService(
        db_path=payload["db_path"],
        approved_roots=payload["approved_roots"],
    )
    try:
        rec = svc.approve(payload["run_id"], payload["reviewer_id"], payload["comment"])
        return ("ok", rec.status)
    except ApprovalConflictError:
        return ("conflict", None)
    except Exception as e:
        return ("error", str(e))


def _cross_process_worker_reject_receipt(payload: dict):
    from governance.approval import ApprovalService, ApprovalConflictError

    svc = ApprovalService(
        db_path=payload["db_path"],
        approved_roots=payload["approved_roots"],
    )
    try:
        rec = svc.reject(
            payload["run_id"], payload["reviewer_id"], payload["comment"]
        )
        return ("ok", rec.status)
    except ApprovalConflictError:
        return ("conflict", None)
    except Exception as e:
        return ("error", str(e))


def _cross_process_receipt_race(*, db_path: str, approved_roots: list, run_id: str):
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
                (_cross_process_worker_approve_receipt, payload),
                (_cross_process_worker_reject_receipt, payload),
            ],
        )
    return outcomes


def _cross_process_worker_wrapper(args):
    fn, payload = args
    return fn(payload)
