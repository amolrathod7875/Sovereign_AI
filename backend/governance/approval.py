"""Governance package: persistent human approval gate.

Implements a strict local approval state machine backed by SQLite.
No cloud dependency. No PostgreSQL dependency.
"""
import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

DB_PATH_ENV = "SOVEREIGN_APPROVAL_DB"


def _default_db_path() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "data" / "governance" / "approvals.sqlite3")


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalNotFoundError(Exception):
    """Raised when an approval record does not exist."""


class ApprovalConflictError(Exception):
    """Raised when an approval state transition is invalid or a run binding conflicts."""


class ArtifactIntegrityError(Exception):
    """Raised when an artifact hash does not match the stored pending hash."""


@dataclass
class ApprovalRecord:
    run_id: str
    asset_tag: str
    decision: str
    approval_required: int
    status: str
    reviewer_id: Optional[str]
    reviewer_comment: Optional[str]
    reviewer_identity_verified: int
    created_at: str
    reviewed_at: Optional[str]
    artifact_path: str
    artifact_sha256: str
    artifact_verification_ok: int
    identity_status: Optional[str]
    external_calls: int
    run_snapshot_json: str
    record_version: int

    @property
    def snapshot(self) -> dict:
        try:
            return json.loads(self.run_snapshot_json)
        except Exception:
            return {}


_LOCK = threading.Lock()


class ApprovalService:
    def __init__(
        self,
        db_path: Optional[str] = None,
        approved_roots: Optional[List[str]] = None,
    ):
        self.db_path = db_path or os.environ.get(DB_PATH_ENV) or _default_db_path()
        self.approved_roots = [str(Path(r).resolve()) for r in (approved_roots or [])]
        if not self.approved_roots:
            repo_root = Path(__file__).resolve().parents[2]
            try:
                from app.config import settings as _app_settings

                for p in (_app_settings.AGENT_OUTPUT_DIR, _app_settings.ARTIFACT_DIR):
                    r = str(Path(p).resolve())
                    if r not in self.approved_roots:
                        self.approved_roots.append(r)
            except Exception:
                pass
            try:
                from agent.config import OUTPUT_DIR as _agent_out

                r = str(Path(_agent_out).resolve())
                if r not in self.approved_roots:
                    self.approved_roots.append(r)
            except Exception:
                pass
            for p in [repo_root / "data" / "outputs", repo_root / "data" / "artifacts"]:
                r = str(p.resolve())
                if r not in self.approved_roots:
                    self.approved_roots.append(r)
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.isolation_level = None
        return conn

    def _ensure_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_records (
                    run_id TEXT PRIMARY KEY,
                    asset_tag TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    approval_required INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    reviewer_id TEXT NULL,
                    reviewer_comment TEXT NULL,
                    reviewer_identity_verified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT NULL,
                    artifact_path TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    artifact_verification_ok INTEGER NOT NULL,
                    identity_status TEXT NULL,
                    external_calls INTEGER NOT NULL DEFAULT 0,
                    run_snapshot_json TEXT NOT NULL,
                    record_version INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_approval_status ON approval_records(status)"
            )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _is_path_approved(self, path: str) -> bool:
        try:
            p = str(Path(path).resolve())
        except Exception:
            return False
        for root in self.approved_roots:
            if p == root or p.startswith(root + os.sep):
                return True
        return False

    def _compute_sha256(self, path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _snapshot_from_result(self, result: dict) -> str:
        data = {
            "run_id": result.get("run_id"),
            "status": result.get("status"),
            "asset_identity": result.get("asset_identity"),
            "retrieval_summary": result.get("retrieval_summary"),
            "calculations_summary": result.get("calculations_summary"),
            "decision": result.get("decision"),
            "reasoning_summary": result.get("reasoning_summary"),
            "approval_required": result.get("approval_required"),
            "required_actions": result.get("required_actions"),
            "supporting_evidence": result.get("supporting_evidence"),
            "artifacts": result.get("artifacts"),
            "verification": result.get("verification"),
            "external_calls": result.get("external_calls"),
            "routing": result.get("routing"),
            "trace": result.get("trace"),
            "vision_evidence": result.get("vision_evidence"),
            "vision_tags": result.get("vision_tags"),
            "input_binding": result.get("input_binding"),
        }
        return json.dumps(data, default=str)

    def create_pending_from_run(self, result: dict) -> Optional[ApprovalRecord]:
        approval_required = bool(result.get("approval_required"))
        if not approval_required:
            return None

        run_id = (result.get("run_id") or "").strip()
        decision = (result.get("decision") or "").strip()
        artifacts = result.get("artifacts") or []
        verification = result.get("verification") or {}
        identity = result.get("asset_identity") or {}
        external_calls = int(result.get("external_calls") or 0)

        if not run_id:
            raise ApprovalConflictError("run_id is empty")
        if not decision:
            raise ApprovalConflictError("decision is empty")
        if not artifacts:
            raise ApprovalConflictError("missing artifact")
        if not verification.get("ok"):
            raise ApprovalConflictError("artifact verification failed")
        canonical_tag = identity.get("canonical_tag")
        asset_tag = (result.get("asset_tag") or "").strip()
        if not canonical_tag and not asset_tag:
            raise ApprovalConflictError("missing asset identity")

        artifact_path = artifacts[0]
        if not self._is_path_approved(artifact_path):
            raise ApprovalConflictError(
                f"artifact path outside approved roots: {artifact_path}"
            )
        if not Path(artifact_path).is_file():
            raise ApprovalConflictError(f"artifact is not a file: {artifact_path}")

        try:
            sha256 = self._compute_sha256(artifact_path)
        except Exception as e:
            raise ApprovalConflictError(f"cannot compute artifact sha256: {e}")

        snapshot = self._snapshot_from_result(result)
        now = self._now()
        record = ApprovalRecord(
            run_id=run_id,
            asset_tag=asset_tag or canonical_tag or "",
            decision=decision,
            approval_required=int(approval_required),
            status=ApprovalStatus.PENDING,
            reviewer_id=None,
            reviewer_comment=None,
            reviewer_identity_verified=0,
            created_at=now,
            reviewed_at=None,
            artifact_path=artifact_path,
            artifact_sha256=sha256,
            artifact_verification_ok=int(bool(verification.get("ok"))),
            identity_status=identity.get("status"),
            external_calls=external_calls,
            run_snapshot_json=snapshot,
            record_version=1,
        )

        with _LOCK:
            with self._connect() as conn:
                cur = conn.execute(
                    "SELECT artifact_sha256, decision FROM approval_records WHERE run_id = ?",
                    (run_id,),
                )
                row = cur.fetchone()
                if row:
                    existing_sha = row["artifact_sha256"]
                    existing_decision = row["decision"]
                    if existing_sha != sha256 or existing_decision != decision:
                        raise ApprovalConflictError(
                            f"run_id {run_id} already bound to different evidence"
                        )
                    cur2 = conn.execute(
                        "SELECT * FROM approval_records WHERE run_id = ?", (run_id,)
                    )
                    r = cur2.fetchone()
                    return ApprovalRecord(**dict(r))

                conn.execute(
                    """
                    INSERT INTO approval_records (
                        run_id, asset_tag, decision, approval_required, status,
                        reviewer_id, reviewer_comment, reviewer_identity_verified,
                        created_at, reviewed_at, artifact_path, artifact_sha256,
                        artifact_verification_ok, identity_status, external_calls,
                        run_snapshot_json, record_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.run_id,
                        record.asset_tag,
                        record.decision,
                        record.approval_required,
                        record.status,
                        record.reviewer_id,
                        record.reviewer_comment,
                        record.reviewer_identity_verified,
                        record.created_at,
                        record.reviewed_at,
                        record.artifact_path,
                        record.artifact_sha256,
                        record.artifact_verification_ok,
                        record.identity_status,
                        record.external_calls,
                        record.run_snapshot_json,
                        record.record_version,
                    ),
                )
                return record

    def get_record(self, run_id: str) -> ApprovalRecord:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM approval_records WHERE run_id = ?", (run_id,)
            )
            row = cur.fetchone()
            if not row:
                raise ApprovalNotFoundError(f"approval record not found: {run_id}")
            return ApprovalRecord(**dict(row))

    def list_pending(self) -> List[ApprovalRecord]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM approval_records WHERE status = ? ORDER BY created_at ASC",
                (ApprovalStatus.PENDING,),
            )
            return [ApprovalRecord(**dict(r)) for r in cur.fetchall()]

    def approve(self, run_id: str, reviewer_id: str, comment: Optional[str] = None) -> ApprovalRecord:
        if not reviewer_id or not str(reviewer_id).strip():
            raise ApprovalConflictError("reviewer_id must not be empty")
        reviewer_id = str(reviewer_id).strip()
        return self._transition(
            run_id=run_id,
            new_status=ApprovalStatus.APPROVED,
            reviewer_id=reviewer_id,
            comment=comment,
        )

    def reject(self, run_id: str, reviewer_id: str, comment: str) -> ApprovalRecord:
        if not reviewer_id or not str(reviewer_id).strip():
            raise ApprovalConflictError("reviewer_id must not be empty")
        if not comment or not str(comment).strip():
            raise ApprovalConflictError("rejection comment must not be empty")
        reviewer_id = str(reviewer_id).strip()
        comment = str(comment).strip()
        return self._transition(
            run_id=run_id,
            new_status=ApprovalStatus.REJECTED,
            reviewer_id=reviewer_id,
            comment=comment,
        )

    def _transition(
        self,
        run_id: str,
        new_status: ApprovalStatus,
        reviewer_id: str,
        comment: Optional[str],
    ) -> ApprovalRecord:
        with _LOCK:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "SELECT status, artifact_path, artifact_sha256 FROM approval_records WHERE run_id = ?",
                    (run_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise ApprovalNotFoundError(f"approval record not found: {run_id}")
                current_status = row["status"]
                if current_status != ApprovalStatus.PENDING:
                    raise ApprovalConflictError(
                        f"invalid transition from {current_status} to {new_status}"
                    )
                artifact_path = row["artifact_path"]
                stored_sha = row["artifact_sha256"]
                if not Path(artifact_path).is_file():
                    raise ArtifactIntegrityError(f"artifact missing: {artifact_path}")
                current_sha = self._compute_sha256(artifact_path)
                if current_sha != stored_sha:
                    raise ArtifactIntegrityError(
                        f"artifact hash mismatch: expected {stored_sha}, got {current_sha}"
                    )
                now = self._now()
                conn.execute(
                    """
                    UPDATE approval_records
                    SET status = ?, reviewer_id = ?, reviewer_comment = ?,
                        reviewed_at = ?, reviewer_identity_verified = ?
                    WHERE run_id = ? AND status = ?
                    """,
                    (
                        new_status.value,
                        reviewer_id,
                        comment,
                        now,
                        0,
                        run_id,
                        ApprovalStatus.PENDING,
                    ),
                )
                cur = conn.execute("SELECT changes()")
                if cur.fetchone()[0] != 1:
                    raise ApprovalConflictError(
                        f"concurrent transition failed for {run_id}"
                    )
                terminal_cur = conn.execute(
                    "SELECT * FROM approval_records WHERE run_id = ?",
                    (run_id,),
                )
                terminal_row = terminal_cur.fetchone()
                if not terminal_row:
                    raise ApprovalConflictError(
                        f"terminal approval record missing after transition: {run_id}"
                    )
                terminal_record = ApprovalRecord(**dict(terminal_row))
                try:
                    from governance.receipt import ReceiptService, _compute_receipt_sha256

                    receipt_svc = ReceiptService(
                        db_path=self.db_path, approved_roots=self.approved_roots
                    )
                    payload = receipt_svc._build_payload(
                        terminal_record, terminal_record.snapshot, now
                    )
                    receipt_id = receipt_svc._build_receipt_id(run_id)
                    receipt_sha256 = _compute_receipt_sha256(payload)
                    receipt_svc._ensure_schema(conn)
                    receipt_svc._insert(
                        conn,
                        run_id=run_id,
                        receipt_id=receipt_id,
                        schema_version="1.0",
                        created_at=now,
                        approval_status=new_status.value,
                        artifact_sha256=terminal_record.artifact_sha256,
                        payload=payload,
                        receipt_sha256=receipt_sha256,
                    )
                except Exception as receipt_error:
                    raise ApprovalConflictError(
                        f"sovereignty receipt creation failed for {run_id}: {receipt_error}"
                    ) from receipt_error
                try:
                    from governance.receipt_chain import ReceiptChainService

                    chain_svc = ReceiptChainService(db_path=self.db_path)
                    chain_svc._append_in_transaction(
                        conn=conn,
                        run_id=run_id,
                        receipt_id=receipt_id,
                        receipt_sha256=receipt_sha256,
                        approval_status=new_status.value,
                        linked_at=now,
                    )
                except Exception as chain_error:
                    raise ApprovalConflictError(
                        f"receipt chain append failed for {run_id}: {chain_error}"
                    ) from chain_error
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            finally:
                conn.close()

        return self.get_record(run_id)
