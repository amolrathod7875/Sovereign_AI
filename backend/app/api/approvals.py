"""Approval governance API.

Exposes:
  GET  /api/approvals/pending
  GET  /api/approvals/{run_id}
  POST /api/approvals/{run_id}/approve
  POST /api/approvals/{run_id}/reject
"""
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from governance.approval import (
    ApprovalService,
    ApprovalRecord,
    ApprovalNotFoundError,
    ApprovalConflictError,
    ArtifactIntegrityError,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_service = ApprovalService()

try:
    from agent.config import REPO_ROOT as _REPO_ROOT
except Exception:
    _REPO_ROOT = Path(__file__).resolve().parents[3]


def _logical_path(artifact_path: str) -> str:
    try:
        return str(Path(artifact_path).resolve().relative_to(_REPO_ROOT))
    except Exception:
        return artifact_path


class ApproveRequest(BaseModel):
    reviewer_id: str
    comment: Optional[str] = None


class RejectRequest(BaseModel):
    reviewer_id: str
    comment: str


def _record_to_dict(record: ApprovalRecord) -> dict:
    return {
        "run_id": record.run_id,
        "asset_tag": record.asset_tag,
        "decision": record.decision,
        "approval_required": bool(record.approval_required),
        "status": record.status,
        "reviewer_id": record.reviewer_id,
        "reviewer_comment": record.reviewer_comment,
        "reviewer_identity_verified": bool(record.reviewer_identity_verified),
        "created_at": record.created_at,
        "reviewed_at": record.reviewed_at,
        "artifact_path": _logical_path(record.artifact_path),
        "artifact_sha256": record.artifact_sha256,
        "artifact_verification_ok": bool(record.artifact_verification_ok),
        "identity_status": record.identity_status,
        "external_calls": record.external_calls,
    }


@router.get("/pending")
async def get_pending() -> List[dict]:
    records = _service.list_pending()
    return [_record_to_dict(r) for r in records]


@router.get("/{run_id}")
async def get_record(run_id: str) -> dict:
    try:
        record = _service.get_record(run_id)
    except ApprovalNotFoundError:
        raise HTTPException(status_code=404, detail="approval record not found")
    except ApprovalConflictError:
        raise HTTPException(status_code=409, detail="approval conflict")
    return _record_to_dict(record)


@router.post("/{run_id}/approve")
async def approve_run(run_id: str, body: ApproveRequest) -> dict:
    reviewer_id = (body.reviewer_id or "").strip()
    if not reviewer_id:
        raise HTTPException(status_code=422, detail="reviewer_id must not be empty")
    try:
        record = _service.approve(run_id, reviewer_id, body.comment)
    except ApprovalNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ArtifactIntegrityError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ApprovalConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _record_to_dict(record)


@router.post("/{run_id}/reject")
async def reject_run(run_id: str, body: RejectRequest) -> dict:
    reviewer_id = (body.reviewer_id or "").strip()
    comment = (body.comment or "").strip()
    if not reviewer_id:
        raise HTTPException(status_code=422, detail="reviewer_id must not be empty")
    if not comment:
        raise HTTPException(status_code=422, detail="rejection comment must not be empty")
    try:
        record = _service.reject(run_id, reviewer_id, comment)
    except ApprovalNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ArtifactIntegrityError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ApprovalConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _record_to_dict(record)
