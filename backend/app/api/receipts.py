"""Receipt governance API.

Exposes:
  GET /api/receipts/{run_id}
  GET /api/receipts/{run_id}/verify

Receipt creation is atomic with terminal human review and happens ONLY through
POST /api/approvals/{run_id}/approve or /reject.
"""
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from governance.approval import ApprovalService, ApprovalStatus
from governance.receipt import (
    ReceiptIntegrityError,
    ReceiptNotReadyError,
    ReceiptNotFoundError,
    ReceiptRecord,
    ReceiptService,
    ReceiptConflictError,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_service = ReceiptService()

try:
    from agent.config import REPO_ROOT as _REPO_ROOT
except Exception:
    _REPO_ROOT = Path(__file__).resolve().parents[3]


def _logical_path(artifact_path: str) -> str:
    try:
        return str(Path(artifact_path).resolve().relative_to(_REPO_ROOT))
    except Exception:
        return artifact_path


def _record_to_dict(record: ReceiptRecord) -> Dict[str, Any]:
    return {
        "run_id": record.run_id,
        "receipt_id": record.receipt_id,
        "schema_version": record.schema_version,
        "created_at": record.created_at,
        "approval_status": record.approval_status,
        "artifact_sha256": record.artifact_sha256,
        "payload": record.payload,
        "receipt_sha256": record.receipt_sha256,
    }


def _raise_for_pending(run_id: str) -> None:
    try:
        ApprovalService(db_path=_service.db_path).get_record(run_id)
    except Exception:
        raise HTTPException(status_code=404, detail="approval record not found")


@router.get("/{run_id}")
async def get_receipt(run_id: str) -> Dict[str, Any]:
    _raise_for_pending(run_id)
    try:
        record = _service.get_receipt(run_id)
    except ReceiptNotFoundError:
        raise HTTPException(status_code=409, detail="approval not yet terminal")
    return _record_to_dict(record)


@router.get("/{run_id}/verify")
async def verify_receipt(run_id: str) -> Dict[str, Any]:
    _raise_for_pending(run_id)
    try:
        result = _service.verify_receipt(run_id)
    except ReceiptNotFoundError:
        return {
            "valid": False,
            "checks": {"receipt_exists": False},
            "receipt_sha256": None,
        }
    return result
