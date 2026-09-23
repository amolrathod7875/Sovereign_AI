"""Phase 15C1 — Tamper-Evident Sovereignty Receipt Hash Chain Tests.

CPU ONLY. No GPU. No model server. No network.
"""
import hashlib
import json
import multiprocessing
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

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
    build_receipt_payload,
)
from governance.receipt_chain import (
    CHAIN_SCHEMA_VERSION,
    GENESIS_PREVIOUS_HASH,
    ReceiptChainEntry,
    ReceiptChainNotFoundError,
    ReceiptChainConflictError,
    ReceiptChainIntegrityError,
    ReceiptChainService,
    _canonicalize_chain_material,
    _compute_chain_sha256,
    _build_chain_material,
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


def _make_temp_chain_service(tmp_path: Path, **kwargs):
    db_path = str(tmp_path / "approvals.sqlite3")
    return ReceiptChainService(db_path=db_path, **kwargs)


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


def _approve_run(tmp_path: Path, run_id: str, reviewer_id: str = "reviewer-a", comment: str = "ok"):
    art = _write_artifact(tmp_path / f"{run_id}.docx")
    result = _fake_run_result(run_id, str(art))
    svc = _make_temp_service(tmp_path)
    svc.create_pending_from_run(result)
    return svc.approve(run_id, reviewer_id, comment)


def _reject_run(tmp_path: Path, run_id: str, reviewer_id: str = "reviewer-b", comment: str = "bad"):
    art = _write_artifact(tmp_path / f"{run_id}.docx")
    result = _fake_run_result(run_id, str(art))
    svc = _make_temp_service(tmp_path)
    svc.create_pending_from_run(result)
    return svc.reject(run_id, reviewer_id, comment)


class TestEmptyChain:
    def test_empty_chain_is_valid(self, tmp_path: Path):
        svc = _make_temp_chain_service(tmp_path)
        result = svc.verify_chain()
        assert result["valid"] is True
        assert result["status"] == "VALID"
        assert result["entry_count"] == 0
        assert result["head_sequence"] is None
        assert result["head_chain_sha256"] is None

    def test_empty_chain_list_empty(self, tmp_path: Path):
        svc = _make_temp_chain_service(tmp_path)
        assert svc.list_entries() == []

    def test_empty_chain_head_nulls(self, tmp_path: Path):
        svc = _make_temp_chain_service(tmp_path)
        head = svc.get_head()
        assert head["entry_count"] == 0
        assert head["head_sequence"] is None
        assert head["head_chain_sha256"] is None
        assert head["head_run_id"] is None


class TestGenesisEntry:
    def test_first_entry_sequence_one(self, tmp_path: Path):
        _approve_run(tmp_path, "run_gen_1")
        svc = _make_temp_chain_service(tmp_path)
        entries = svc.list_entries()
        assert len(entries) == 1
        assert entries[0].sequence_no == 1

    def test_first_entry_previous_hash_is_genesis(self, tmp_path: Path):
        _approve_run(tmp_path, "run_gen_2")
        svc = _make_temp_chain_service(tmp_path)
        entries = svc.list_entries()
        assert entries[0].previous_chain_sha256 == GENESIS_PREVIOUS_HASH

    def test_first_chain_hash_recomputes(self, tmp_path: Path):
        _approve_run(tmp_path, "run_gen_3")
        svc = _make_temp_chain_service(tmp_path)
        entry = svc.get_entry("run_gen_3")
        material = _build_chain_material(
            sequence_no=entry.sequence_no,
            run_id=entry.run_id,
            receipt_id=entry.receipt_id,
            receipt_sha256=entry.receipt_sha256,
            approval_status=entry.approval_status,
            linked_at=entry.linked_at,
            previous_chain_sha256=entry.previous_chain_sha256,
        )
        recomputed = _compute_chain_sha256(material)
        assert recomputed == entry.chain_sha256


class TestChainLinking:
    def test_second_entry_sequence_two(self, tmp_path: Path):
        _approve_run(tmp_path, "run_link_1")
        _approve_run(tmp_path, "run_link_2")
        svc = _make_temp_chain_service(tmp_path)
        entries = svc.list_entries()
        assert entries[1].sequence_no == 2

    def test_second_entry_previous_hash_is_first_chain_hash(self, tmp_path: Path):
        _approve_run(tmp_path, "run_link_3")
        _approve_run(tmp_path, "run_link_4")
        svc = _make_temp_chain_service(tmp_path)
        entries = svc.list_entries()
        assert entries[1].previous_chain_sha256 == entries[0].chain_sha256

    def test_third_links_to_second(self, tmp_path: Path):
        _approve_run(tmp_path, "run_link_5")
        _approve_run(tmp_path, "run_link_6")
        _approve_run(tmp_path, "run_link_7")
        svc = _make_temp_chain_service(tmp_path)
        entries = svc.list_entries()
        assert entries[2].previous_chain_sha256 == entries[1].chain_sha256

    def test_list_ordered_by_sequence_asc(self, tmp_path: Path):
        _approve_run(tmp_path, "run_ord_1")
        _approve_run(tmp_path, "run_ord_2")
        _approve_run(tmp_path, "run_ord_3")
        svc = _make_temp_chain_service(tmp_path)
        entries = svc.list_entries()
        seqs = [e.sequence_no for e in entries]
        assert seqs == [1, 2, 3]

    def test_head_correct(self, tmp_path: Path):
        _approve_run(tmp_path, "run_head_1")
        _approve_run(tmp_path, "run_head_2")
        _approve_run(tmp_path, "run_head_3")
        svc = _make_temp_chain_service(tmp_path)
        head = svc.get_head()
        assert head["entry_count"] == 3
        assert head["head_sequence"] == 3
        assert head["head_run_id"] == "run_head_3"
        assert head["head_chain_sha256"] == svc.get_entry("run_head_3").chain_sha256


class TestOneChainEntryPerRun:
    def test_exactly_one_chain_entry_per_run(self, tmp_path: Path):
        _approve_run(tmp_path, "run_one_1")
        _approve_run(tmp_path, "run_one_2")
        _approve_run(tmp_path, "run_one_3")
        svc = _make_temp_chain_service(tmp_path)
        entries = svc.list_entries()
        assert len(entries) == 3
        assert {e.run_id for e in entries} == {"run_one_1", "run_one_2", "run_one_3"}

    def test_duplicate_run_rejected_by_state_machine(self, tmp_path: Path):
        _approve_run(tmp_path, "run_dup_1")
        with pytest.raises(ApprovalConflictError):
            _approve_run(tmp_path, "run_dup_1")


class TestChainPersistence:
    def test_chain_survives_restart(self, tmp_path: Path):
        _approve_run(tmp_path, "run_persist_1")
        _approve_run(tmp_path, "run_persist_2")
        svc_b = _make_temp_chain_service(tmp_path)
        entries = svc_b.list_entries()
        assert len(entries) == 2
        svc_b_again = _make_temp_chain_service(tmp_path)
        assert svc_b_again.get_entry("run_persist_1").chain_sha256 == entries[0].chain_sha256

    def test_receipt_sha_unchanged_after_linking(self, tmp_path: Path):
        _approve_run(tmp_path, "run_sha_1")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt_before = receipt_svc.get_receipt("run_sha_1")
        _approve_run(tmp_path, "run_sha_2")
        receipt_after = receipt_svc.get_receipt("run_sha_1")
        assert receipt_after.receipt_sha256 == receipt_before.receipt_sha256


class TestApprovedRejectedCoverage:
    def test_mixed_approved_rejected_chain(self, tmp_path: Path):
        _approve_run(tmp_path, "run_mix_1")
        _reject_run(tmp_path, "run_mix_2")
        _approve_run(tmp_path, "run_mix_3")
        svc = _make_temp_chain_service(tmp_path)
        result = svc.verify_chain()
        assert result["valid"] is True
        entries = svc.list_entries()
        assert entries[0].approval_status == "APPROVED"
        assert entries[1].approval_status == "REJECTED"
        assert entries[2].approval_status == "APPROVED"


class TestChainAtomicRollback:
    def test_approve_chain_failure_rolls_back(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art_atomic.docx")
        result = _fake_run_result("run_atomic_a", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)

        def failing_append(conn, **kwargs):
            raise RuntimeError("chain append failure")

        with patch.object(ReceiptChainService, "_append_in_transaction", new=failing_append):
            with pytest.raises(ApprovalConflictError):
                svc.approve("run_atomic_a", "reviewer-a", "ok")

        record = svc.get_record("run_atomic_a")
        assert record.status == ApprovalStatus.PENDING
        assert record.reviewer_id is None
        assert record.reviewed_at is None
        receipt_svc = _make_temp_receipt_service(tmp_path)
        with pytest.raises(ReceiptNotFoundError):
            receipt_svc.get_receipt("run_atomic_a")
        chain_svc = _make_temp_chain_service(tmp_path)
        assert chain_svc.list_entries() == []

    def test_reject_chain_failure_rolls_back(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art_atomic_r.docx")
        result = _fake_run_result("run_atomic_r", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)

        def failing_append(conn, **kwargs):
            raise RuntimeError("chain append failure")

        with patch.object(ReceiptChainService, "_append_in_transaction", new=failing_append):
            with pytest.raises(ApprovalConflictError):
                svc.reject("run_atomic_r", "reviewer-b", "bad")

        record = svc.get_record("run_atomic_r")
        assert record.status == ApprovalStatus.PENDING
        receipt_svc = _make_temp_receipt_service(tmp_path)
        with pytest.raises(ReceiptNotFoundError):
            receipt_svc.get_receipt("run_atomic_r")
        chain_svc = _make_temp_chain_service(tmp_path)
        assert chain_svc.list_entries() == []


def _chain_race_worker_approve(payload: dict):
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


def _chain_race_worker_reject(payload: dict):
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


def _chain_race_worker_wrapper(args):
    fn, payload = args
    return fn(payload)


def _cross_process_chain_race(*, db_path: str, approved_roots: list, run_id: str):
    payload = {
        "db_path": db_path,
        "approved_roots": approved_roots,
        "run_id": run_id,
        "reviewer_id": "reviewer-x",
        "comment": "race",
    }
    with multiprocessing.Pool(processes=2) as pool:
        outcomes = pool.map(
            _chain_race_worker_wrapper,
            [
                (_chain_race_worker_approve, payload),
                (_chain_race_worker_reject, payload),
            ],
        )
    return outcomes


class TestSameRunRace:
    def test_same_run_race_exactly_one_success(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art_race.docx")
        result = _fake_run_result("run_race", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)

        db_path = str(tmp_path / "approvals.sqlite3")
        approved_roots = [
            str(tmp_path),
            str(REPO.parent / "data" / "outputs"),
            str(REPO.parent / "data" / "artifacts"),
        ]

        outcomes = _cross_process_chain_race(
            db_path=db_path,
            approved_roots=approved_roots,
            run_id="run_race",
        )

        successes = [o for o in outcomes if o[0] == "ok"]
        conflicts = [o for o in outcomes if o[0] == "conflict"]
        errors = [o for o in outcomes if o[0] == "error"]

        assert len(errors) == 0, f"unexpected errors: {errors}"
        assert len(successes) == 1, f"expected exactly 1 success, got {len(successes)}: {successes}"
        assert len(conflicts) == 1, f"expected exactly 1 conflict, got {len(conflicts)}: {conflicts}"

        svc_final = _make_temp_service(tmp_path)
        final = svc_final.get_record("run_race")
        assert final.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED)

        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_race")
        assert receipt.approval_status == final.status

        chain_svc = _make_temp_chain_service(tmp_path)
        entries = chain_svc.list_entries()
        assert len(entries) == 1
        assert entries[0].run_id == "run_race"


class TestDifferentRunCrossProcessRace:
    def test_concurrent_different_runs_both_succeed(self, tmp_path: Path):
        art_a = _write_artifact(tmp_path / "art_a.docx")
        art_b = _write_artifact(tmp_path / "art_b.docx")
        result_a = _fake_run_result("run_diff_a", str(art_a))
        result_b = _fake_run_result("run_diff_b", str(art_b))

        db_path = str(tmp_path / "approvals.sqlite3")
        approved_roots = [
            str(tmp_path),
            str(REPO.parent / "data" / "outputs"),
            str(REPO.parent / "data" / "artifacts"),
        ]

        svc_a = ApprovalService(db_path=db_path, approved_roots=approved_roots)
        svc_b = ApprovalService(db_path=db_path, approved_roots=approved_roots)
        svc_a.create_pending_from_run(result_a)
        svc_b.create_pending_from_run(result_b)

        payload_a = {
            "db_path": db_path,
            "approved_roots": approved_roots,
            "run_id": "run_diff_a",
            "reviewer_id": "ra",
            "comment": "ok",
        }
        payload_b = {
            "db_path": db_path,
            "approved_roots": approved_roots,
            "run_id": "run_diff_b",
            "reviewer_id": "rb",
            "comment": "bad",
        }

        with multiprocessing.Pool(processes=2) as pool:
            outcomes = pool.map(
                _chain_race_worker_wrapper,
                [
                    (_chain_race_worker_approve, payload_a),
                    (_chain_race_worker_reject, payload_b),
                ],
            )

        successes = [o for o in outcomes if o[0] == "ok"]
        errors = [o for o in outcomes if o[0] == "error"]

        assert len(errors) == 0, f"unexpected errors: {errors}"
        assert len(successes) == 2, f"expected 2 successes, got {len(successes)}: {successes}"

        chain_svc = _make_temp_chain_service(tmp_path)
        entries = chain_svc.list_entries()
        assert len(entries) == 2
        seqs = sorted([e.sequence_no for e in entries])
        assert seqs == [1, 2]
        entry_map = {e.run_id: e for e in entries}
        assert entry_map["run_diff_a"].previous_chain_sha256 == GENESIS_PREVIOUS_HASH or \
               entry_map["run_diff_b"].previous_chain_sha256 == GENESIS_PREVIOUS_HASH
        first_seq = min(entry_map.values(), key=lambda e: e.sequence_no)
        second_seq = max(entry_map.values(), key=lambda e: e.sequence_no)
        assert second_seq.previous_chain_sha256 == first_seq.chain_sha256

        verify_result = chain_svc.verify_chain()
        assert verify_result["valid"] is True


class TestReceiptPayloadTamper:
    def test_modified_receipt_payload_detected(self, tmp_path: Path):
        _approve_run(tmp_path, "run_tamper_1")
        _approve_run(tmp_path, "run_tamper_2")
        _approve_run(tmp_path, "run_tamper_3")
        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_tamper_1")
        payload = dict(receipt.payload)
        payload["asset"]["requested_tag"] = "TAMPERED"
        conn = receipt_svc._connect()
        try:
            conn.execute(
                "UPDATE sovereignty_receipts SET payload_json = ? WHERE run_id = ?",
                (json.dumps(payload, default=str), "run_tamper_1"),
            )
        finally:
            conn.close()

        chain_svc = _make_temp_chain_service(tmp_path)
        result = chain_svc.verify_chain()
        assert result["valid"] is False
        receipt_self_invalid = not result["checks"].get("receipt_self_hashes_valid", True)
        assert receipt_self_invalid


class TestRecomputedReceiptHashStillBreaksChain:
    def test_recomputed_receipt_hash_chain_detects_mismatch(self, tmp_path: Path):
        _approve_run(tmp_path, "run_recomp_1")
        _approve_run(tmp_path, "run_recomp_2")
        _approve_run(tmp_path, "run_recomp_3")

        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_recomp_1")
        payload = dict(receipt.payload)
        payload["asset"]["requested_tag"] = "TAMPERED"
        new_receipt_sha = _compute_receipt_sha256(payload)

        conn = receipt_svc._connect()
        try:
            conn.execute(
                "UPDATE sovereignty_receipts SET payload_json = ?, receipt_sha256 = ? WHERE run_id = ?",
                (json.dumps(payload, default=str), new_receipt_sha, "run_recomp_1"),
            )
        finally:
            conn.close()

        chain_svc = _make_temp_chain_service(tmp_path)
        result = chain_svc.verify_chain()
        assert result["valid"] is False
        assert not result["checks"].get("receipt_bindings_valid", True)


class TestChainEntryDataTamper:
    def test_modified_chain_entry_field_detected(self, tmp_path: Path):
        _approve_run(tmp_path, "run_ct_1")
        _approve_run(tmp_path, "run_ct_2")
        chain_svc = _make_temp_chain_service(tmp_path)
        entry = chain_svc.get_entry("run_ct_1")

        conn = chain_svc._connect()
        try:
            conn.execute(
                "UPDATE receipt_chain SET approval_status = ? WHERE sequence_no = ?",
                ("HACKED", entry.sequence_no),
            )
        finally:
            conn.close()

        result = chain_svc.verify_chain()
        assert result["valid"] is False
        assert not result["checks"].get("entry_hashes_valid", True)


class TestRecomputeOldEntryNotDownstream:
    def test_recomputed_old_entry_breaks_downstream_link(self, tmp_path: Path):
        _approve_run(tmp_path, "run_down_1")
        _approve_run(tmp_path, "run_down_2")
        _approve_run(tmp_path, "run_down_3")

        chain_svc = _make_temp_chain_service(tmp_path)
        entry1 = chain_svc.get_entry("run_down_1")
        entry2 = chain_svc.get_entry("run_down_2")

        original_hash = entry1.chain_sha256
        material = _build_chain_material(
            sequence_no=entry1.sequence_no,
            run_id=entry1.run_id,
            receipt_id=entry1.receipt_id,
            receipt_sha256=entry1.receipt_sha256,
            approval_status=entry1.approval_status,
            linked_at=entry1.linked_at,
            previous_chain_sha256=entry1.previous_chain_sha256,
        )
        assert _compute_chain_sha256(material) == original_hash

        fake_previous = "a" * 64
        fake_material = _build_chain_material(
            sequence_no=entry1.sequence_no,
            run_id=entry1.run_id,
            receipt_id=entry1.receipt_id,
            receipt_sha256=entry1.receipt_sha256,
            approval_status=entry1.approval_status,
            linked_at=entry1.linked_at,
            previous_chain_sha256=fake_previous,
        )
        fake_hash = _compute_chain_sha256(fake_material)
        assert fake_hash != original_hash

        conn = chain_svc._connect()
        try:
            conn.execute(
                "UPDATE receipt_chain SET previous_chain_sha256 = ?, chain_sha256 = ? WHERE sequence_no = ?",
                (fake_previous, fake_hash, entry1.sequence_no),
            )
        finally:
            conn.close()

        result = chain_svc.verify_chain()
        assert result["valid"] is False
        assert not result["checks"].get("links_valid", True)


class TestPreviousHashTamper:
    def test_modified_previous_hash_detected(self, tmp_path: Path):
        _approve_run(tmp_path, "run_prev_1")
        _approve_run(tmp_path, "run_prev_2")
        _approve_run(tmp_path, "run_prev_3")

        chain_svc = _make_temp_chain_service(tmp_path)
        entry2 = chain_svc.get_entry("run_prev_2")

        conn = chain_svc._connect()
        try:
            conn.execute(
                "UPDATE receipt_chain SET previous_chain_sha256 = ? WHERE sequence_no = ?",
                (GENESIS_PREVIOUS_HASH, entry2.sequence_no),
            )
        finally:
            conn.close()

        result = chain_svc.verify_chain()
        assert result["valid"] is False
        assert not result["checks"].get("links_valid", True)
        assert not result["checks"].get("entry_hashes_valid", True)


class TestMiddleEntryDeletion:
    def test_deleted_middle_entry_detected(self, tmp_path: Path):
        _approve_run(tmp_path, "run_mid_1")
        _approve_run(tmp_path, "run_mid_2")
        _approve_run(tmp_path, "run_mid_3")

        chain_svc = _make_temp_chain_service(tmp_path)
        entry2 = chain_svc.get_entry("run_mid_2")

        conn = chain_svc._connect()
        try:
            conn.execute("DELETE FROM receipt_chain WHERE sequence_no = ?", (entry2.sequence_no,))
        finally:
            conn.close()

        result = chain_svc.verify_chain()
        assert result["valid"] is False
        assert not result["checks"].get("sequence_contiguous", True)
        assert not result["checks"].get("links_valid", True)


class TestDuplicateReorderSafety:
    def test_duplicate_run_prevented_by_unique(self, tmp_path: Path):
        _approve_run(tmp_path, "run_uniq_1")
        _approve_run(tmp_path, "run_uniq_2")
        chain_svc = _make_temp_chain_service(tmp_path)
        assert len(chain_svc.list_entries()) == 2

        svc = _make_temp_service(tmp_path)
        conn = svc._connect()
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO receipt_chain (sequence_no, run_id, receipt_id, receipt_sha256, approval_status, linked_at, previous_chain_sha256, chain_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        3,
                        "run_uniq_1",
                        "receipt:run_uniq_1",
                        "abc",
                        "APPROVED",
                        "2024-01-01T00:00:00+00:00",
                        "0" * 64,
                        "def",
                    ),
                )
        finally:
            conn.close()


class TestLegacyReceiptDetection:
    def test_unlinked_legacy_receipt_detected(self, tmp_path: Path):
        art = _write_artifact(tmp_path / "art_legacy.docx")
        result = _fake_run_result("run_legacy", str(art))
        svc = _make_temp_service(tmp_path)
        svc.create_pending_from_run(result)
        svc.approve("run_legacy", "reviewer-a", "ok")

        receipt_svc = _make_temp_receipt_service(tmp_path)
        receipt = receipt_svc.get_receipt("run_legacy")
        assert receipt.receipt_id == _build_receipt_id("run_legacy")

        conn = svc._connect()
        try:
            conn.execute("DELETE FROM receipt_chain WHERE run_id = ?", ("run_legacy",))
        finally:
            conn.close()

        chain_svc = _make_temp_chain_service(tmp_path)
        with pytest.raises(ReceiptChainNotFoundError):
            chain_svc.get_entry("run_legacy")

        verify_result = chain_svc.verify_chain()
        assert verify_result["valid"] is False
        assert not verify_result["checks"].get("unlinked_receipts_absent", True)


class TestCanonicalHashDeterminism:
    def test_chain_hash_deterministic_regardless_of_dict_order(self, tmp_path: Path):
        material = {
            "chain_schema_version": "1.0",
            "sequence_no": 1,
            "run_id": "run_hash",
            "receipt_id": "receipt:run_hash",
            "receipt_sha256": "abc",
            "approval_status": "APPROVED",
            "linked_at": "2024-01-01T00:00:00+00:00",
            "previous_chain_sha256": "0" * 64,
        }
        canonical1 = _canonicalize_chain_material(material)
        material_reversed = dict(reversed(list(material.items())))
        canonical2 = _canonicalize_chain_material(material_reversed)
        assert canonical1 == canonical2
        assert _compute_chain_sha256(material) == _compute_chain_sha256(material_reversed)

    def test_one_byte_change_different_hash(self, tmp_path: Path):
        material1 = {
            "chain_schema_version": "1.0",
            "sequence_no": 1,
            "run_id": "run_hash2",
            "receipt_id": "receipt:run_hash2",
            "receipt_sha256": "abc",
            "approval_status": "APPROVED",
            "linked_at": "2024-01-01T00:00:00+00:00",
            "previous_chain_sha256": "0" * 64,
        }
        material2 = dict(material1)
        material2["approval_status"] = "REJECTED"
        assert _compute_chain_sha256(material1) != _compute_chain_sha256(material2)


class TestChainAPI:
    def test_get_chain_returns_200(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipt_chain as chain_router

        _approve_run(tmp_path, "run_api_1")
        svc = _make_temp_chain_service(tmp_path)
        chain_router._service = svc
        app = FastAPI()
        app.include_router(chain_router.router, prefix="/api/receipt-chain")
        client = TestClient(app)
        resp = client.get("/api/receipt-chain")
        assert resp.status_code == 200
        body = resp.json()
        assert body["entry_count"] == 1
        assert len(body["entries"]) == 1

    def test_get_head_returns_200(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipt_chain as chain_router

        _approve_run(tmp_path, "run_api_head")
        svc = _make_temp_chain_service(tmp_path)
        chain_router._service = svc
        app = FastAPI()
        app.include_router(chain_router.router, prefix="/api/receipt-chain")
        client = TestClient(app)
        resp = client.get("/api/receipt-chain/head")
        assert resp.status_code == 200
        body = resp.json()
        assert body["entry_count"] == 1
        assert body["head_sequence"] == 1

    def test_get_verify_returns_200_valid(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipt_chain as chain_router

        _approve_run(tmp_path, "run_api_verify")
        svc = _make_temp_chain_service(tmp_path)
        chain_router._service = svc
        app = FastAPI()
        app.include_router(chain_router.router, prefix="/api/receipt-chain")
        client = TestClient(app)
        resp = client.get("/api/receipt-chain/verify")
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_get_verify_returns_200_invalid_on_tamper(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipt_chain as chain_router

        _approve_run(tmp_path, "run_api_tamper")
        svc = _make_temp_chain_service(tmp_path)
        entry = svc.get_entry("run_api_tamper")
        conn = svc._connect()
        try:
            conn.execute(
                "UPDATE receipt_chain SET approval_status = ? WHERE sequence_no = ?",
                ("HACKED", entry.sequence_no),
            )
        finally:
            conn.close()
        chain_router._service = svc
        app = FastAPI()
        app.include_router(chain_router.router, prefix="/api/receipt-chain")
        client = TestClient(app)
        resp = client.get("/api/receipt-chain/verify")
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_get_entry_known_run_200(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipt_chain as chain_router

        _approve_run(tmp_path, "run_api_known")
        svc = _make_temp_chain_service(tmp_path)
        chain_router._service = svc
        app = FastAPI()
        app.include_router(chain_router.router, prefix="/api/receipt-chain")
        client = TestClient(app)
        resp = client.get("/api/receipt-chain/run_api_known")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == "run_api_known"

    def test_get_entry_unknown_run_404(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipt_chain as chain_router

        svc = _make_temp_chain_service(tmp_path)
        chain_router._service = svc
        app = FastAPI()
        app.include_router(chain_router.router, prefix="/api/receipt-chain")
        client = TestClient(app)
        resp = client.get("/api/receipt-chain/run_unknown")
        assert resp.status_code == 404

    def test_no_chain_mutation_endpoints(self, tmp_path: Path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api import receipt_chain as chain_router

        app = FastAPI()
        app.include_router(chain_router.router, prefix="/api/receipt-chain")
        client = TestClient(app)
        for method_url in [
            ("POST", "/api/receipt-chain"),
            ("PUT", "/api/receipt-chain/run_x"),
            ("PATCH", "/api/receipt-chain/run_x"),
            ("DELETE", "/api/receipt-chain/run_x"),
        ]:
            method, url = method_url
            resp = getattr(client, method.lower())(url)
            assert resp.status_code == 405, f"expected 405 for {method} {url}, got {resp.status_code}"
