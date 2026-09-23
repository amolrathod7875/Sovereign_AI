"""Governance package: sovereignty receipt.

Implements a deterministic, SHA256-bound receipt for every terminal human review
decision. The receipt is built from stored approval evidence and committed
atomically with the approval transition.

Phase 15B does NOT yet implement an append-only previous-receipt hash chain.
"""
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from pathlib import Path

if TYPE_CHECKING:
    from governance.approval import ApprovalRecord


class ReceiptNotFoundError(Exception):
    """Raised when a sovereignty receipt does not exist."""


class ReceiptNotReadyError(Exception):
    """Raised when a receipt is requested for a PENDING approval."""


class ReceiptConflictError(Exception):
    """Raised when receipt insertion conflicts with an existing receipt."""


class ReceiptIntegrityError(Exception):
    """Raised when stored receipt self-hash or approval binding is invalid."""


@dataclass
class ReceiptRecord:
    run_id: str
    receipt_id: str
    schema_version: str
    created_at: str
    approval_status: str
    artifact_sha256: str
    payload_json: str
    receipt_sha256: str

    @property
    def payload(self) -> Dict[str, Any]:
        try:
            return json.loads(self.payload_json)
        except Exception:
            return {}


def _canonicalize(payload: Dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _compute_receipt_sha256(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonicalize(payload)).hexdigest()


def _build_receipt_id(run_id: str) -> str:
    return f"receipt:{run_id}"


def _safe_trace_nodes(trace: Any) -> List[str]:
    nodes: List[str] = []
    if not isinstance(trace, list):
        return nodes
    for entry in trace:
        if isinstance(entry, dict):
            node = entry.get("node") or entry.get("name") or entry.get("step")
            if node:
                nodes.append(str(node))
    return nodes


def _logical_path(artifact_path: str, repo_root: Optional[Path]) -> str:
    try:
        p = Path(artifact_path).resolve()
        if repo_root is not None:
            return str(p.relative_to(repo_root.resolve()))
    except Exception:
        pass
    return artifact_path


def _vision_models_from_evidence(vision_evidence: Any) -> List[str]:
    models: List[str] = []
    if not isinstance(vision_evidence, list):
        return models
    for entry in vision_evidence:
        if isinstance(entry, dict):
            model = entry.get("model")
            if model:
                models.append(str(model))
    return models


def build_receipt_payload(
    approval_record: "ApprovalRecord",
    snapshot: Dict[str, Any],
    now: str,
) -> Dict[str, Any]:
    asset_identity = snapshot.get("asset_identity") or {}
    asset_tag = approval_record.asset_tag or asset_identity.get("canonical_tag") or ""
    retrieval = snapshot.get("retrieval_summary") or {}
    calculations = snapshot.get("calculations_summary") or {}
    routing = snapshot.get("routing") or {}
    if not isinstance(routing, dict):
        routing = {}

    trace = snapshot.get("trace") or []
    executed_nodes = _safe_trace_nodes(trace)

    artifact_logical = _logical_path(
        approval_record.artifact_path,
        Path(__file__).resolve().parents[2],
    )

    recorded_models = _vision_models_from_evidence(
        snapshot.get("vision_evidence") or []
    )
    if recorded_models:
        model_execution_status = "EXPLICIT_VISION_EVIDENCE"
    else:
        model_execution_status = "NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE"

    return {
        "schema_version": "1.0",
        "receipt_id": _build_receipt_id(approval_record.run_id),
        "run_id": approval_record.run_id,
        "created_at": now,
        "asset": {
            "requested_tag": asset_tag,
            "canonical_tag": asset_identity.get("canonical_tag"),
            "identity_status": asset_identity.get("status"),
        },
        "ai_recommendation": {
            "decision": snapshot.get("decision"),
            "approval_required": snapshot.get("approval_required"),
            "required_actions": snapshot.get("required_actions") or [],
            "reasoning_summary": snapshot.get("reasoning_summary"),
        },
        "human_review": {
            "status": approval_record.status,
            "reviewer_id": approval_record.reviewer_id,
            "reviewer_comment": approval_record.reviewer_comment,
            "reviewer_identity_verified": bool(approval_record.reviewer_identity_verified),
            "approval_created_at": approval_record.created_at,
            "reviewed_at": approval_record.reviewed_at,
        },
        "artifact": {
            "logical_path": artifact_logical,
            "sha256": approval_record.artifact_sha256,
            "verification_ok": bool(approval_record.artifact_verification_ok),
        },
        "retrieval": {
            "chunk_count": retrieval.get("chunk_count"),
            "unique_asset_tags": retrieval.get("unique_asset_tags") or [],
            "source_files": retrieval.get("source_files") or [],
            "document_types": retrieval.get("document_types") or [],
            "retrieval_modes": retrieval.get("retrieval_modes") or [],
        },
        "execution": {
            "executed_nodes": executed_nodes,
            "sandbox_used": bool(calculations.get("sandbox_used")),
        },
        "routing": {
            "task_type": routing.get("task_type"),
            "selected_model": routing.get("selected_model"),
            "models_required": routing.get("models_required") or [],
            "requires_rag": routing.get("requires_rag"),
            "requires_tools": routing.get("requires_tools"),
            "local_only": routing.get("local_only"),
            "all_local": routing.get("all_local"),
        },
        "model_execution": {
            "recorded_models": recorded_models,
            "status": model_execution_status,
        },
        "sovereignty": {
            "external_calls_recorded": approval_record.external_calls,
            "network_guard_scope": "application-level agent run",
            "whole_machine_airgap_certified": False,
        },
    }


class ReceiptService:
    def __init__(
        self,
        db_path: Optional[str] = None,
        approved_roots: Optional[List[str]] = None,
    ):
        self.approved_roots = [str(Path(r).resolve()) for r in (approved_roots or [])]
        if db_path is not None:
            self.db_path = db_path
        else:
            from governance.approval import ApprovalService

            self.db_path = ApprovalService(db_path=db_path, approved_roots=approved_roots).db_path

    def _connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.isolation_level = None
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sovereignty_receipts (
                run_id TEXT PRIMARY KEY,
                receipt_id TEXT NOT NULL UNIQUE,
                schema_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                approval_status TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                receipt_sha256 TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES approval_records(run_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_receipt_approval_status ON sovereignty_receipts(approval_status)"
        )

    def ensure_receipt_schema(self) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)

    def _build_receipt_id(self, run_id: str) -> str:
        return _build_receipt_id(run_id)

    def _build_payload(
        self,
        approval_record: "ApprovalRecord",
        snapshot: Dict[str, Any],
        now: str,
    ) -> Dict[str, Any]:
        return build_receipt_payload(approval_record, snapshot, now)

    def _insert(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        receipt_id: str,
        schema_version: str,
        created_at: str,
        approval_status: str,
        artifact_sha256: str,
        payload: Dict[str, Any],
        receipt_sha256: str,
    ) -> None:
        try:
            conn.execute(
                """
                INSERT INTO sovereignty_receipts (
                    run_id, receipt_id, schema_version, created_at,
                    approval_status, artifact_sha256, payload_json, receipt_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    receipt_id,
                    schema_version,
                    created_at,
                    approval_status,
                    artifact_sha256,
                    json.dumps(payload, default=str),
                    receipt_sha256,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ReceiptConflictError(f"sovereignty receipt conflict for {run_id}: {exc}") from exc

    def get_receipt(self, run_id: str) -> ReceiptRecord:
        with self._connect() as conn:
            try:
                cur = conn.execute(
                    "SELECT * FROM sovereignty_receipts WHERE run_id = ?",
                    (run_id,),
                )
            except sqlite3.OperationalError:
                raise ReceiptNotFoundError(f"sovereignty receipt not found: {run_id}")
            row = cur.fetchone()
            if not row:
                raise ReceiptNotFoundError(f"sovereignty receipt not found: {run_id}")
            return ReceiptRecord(
                run_id=row["run_id"],
                receipt_id=row["receipt_id"],
                schema_version=row["schema_version"],
                created_at=row["created_at"],
                approval_status=row["approval_status"],
                artifact_sha256=row["artifact_sha256"],
                payload_json=row["payload_json"],
                receipt_sha256=row["receipt_sha256"],
            )

    def verify_receipt(self, run_id: str) -> Dict[str, Any]:
        try:
            receipt = self.get_receipt(run_id)
        except ReceiptNotFoundError:
            return {
                "valid": False,
                "checks": {"receipt_exists": False},
                "receipt_sha256": None,
            }

        checks: Dict[str, Any] = {}
        checks["receipt_exists"] = True

        payload = receipt.payload
        if not payload:
            checks["payload_decode"] = False
            return {"valid": False, "checks": checks, "receipt_sha256": receipt.receipt_sha256}
        checks["payload_decode"] = True

        computed_hash = _compute_receipt_sha256(payload)
        checks["payload_hash_matches"] = computed_hash == receipt.receipt_sha256

        checks["run_id_matches"] = payload.get("run_id") == receipt.run_id
        checks["approval_status_matches"] = payload.get("human_review", {}).get("status") == receipt.approval_status

        try:
            from governance.approval import ApprovalService

            approval_record = ApprovalService(db_path=self.db_path).get_record(run_id)
            checks["approval_record_exists"] = True
            checks["reviewer_id_matches"] = payload.get("human_review", {}).get("reviewer_id") == approval_record.reviewer_id
            checks["reviewer_verified_matches"] = payload.get("human_review", {}).get("reviewer_identity_verified") == bool(approval_record.reviewer_identity_verified)
            checks["reviewed_at_matches"] = payload.get("human_review", {}).get("reviewed_at") == approval_record.reviewed_at
            checks["artifact_sha_matches"] = payload.get("artifact", {}).get("sha256") == approval_record.artifact_sha256
            checks["external_calls_matches"] = payload.get("sovereignty", {}).get("external_calls_recorded") == approval_record.external_calls
        except Exception:
            checks["approval_record_exists"] = False

        artifact_current_exists = Path(approval_record.artifact_path).is_file()
        checks["artifact_current_exists"] = artifact_current_exists
        if artifact_current_exists:
            h = hashlib.sha256()
            with open(approval_record.artifact_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            current_sha = h.hexdigest()
            checks["artifact_current_sha_matches"] = current_sha == approval_record.artifact_sha256
        else:
            checks["artifact_current_sha_matches"] = False

        valid = all(
            v is True or v == 1
            for k, v in checks.items()
            if k.endswith("_matches") or k == "receipt_exists"
        )
        return {"valid": valid, "checks": checks, "receipt_sha256": receipt.receipt_sha256}
