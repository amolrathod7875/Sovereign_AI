"""Receipt chain governance API.

Exposes read-only:
  GET /api/receipt-chain
  GET /api/receipt-chain/head
  GET /api/receipt-chain/verify
  GET /api/receipt-chain/{run_id}

Chain mutation is NOT exposed through this API. Chain entries are appended
atomically inside the terminal human review transaction only.
"""
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from governance.receipt_chain import (
    ReceiptChainConflictError,
    ReceiptChainIntegrityError,
    ReceiptChainNotFoundError,
    ReceiptChainService,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_service = ReceiptChainService()


def _entry_to_dict(entry: Any) -> Dict[str, Any]:
    return {
        "sequence_no": entry.sequence_no,
        "run_id": entry.run_id,
        "receipt_id": entry.receipt_id,
        "receipt_sha256": entry.receipt_sha256,
        "approval_status": entry.approval_status,
        "linked_at": entry.linked_at,
        "previous_chain_sha256": entry.previous_chain_sha256,
        "chain_sha256": entry.chain_sha256,
    }


@router.get("")
async def list_chain() -> Dict[str, Any]:
    entries = _service.list_entries()
    head = _service.get_head()
    return {
        "entry_count": head["entry_count"],
        "head": head,
        "entries": [_entry_to_dict(e) for e in entries],
    }


@router.get("/head")
async def get_head() -> Dict[str, Any]:
    head = _service.get_head()
    return head


@router.get("/verify")
async def verify_chain() -> Dict[str, Any]:
    try:
        result = _service.verify_chain()
    except ReceiptChainIntegrityError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.get("/{run_id}")
async def get_entry(run_id: str) -> Dict[str, Any]:
    try:
        entry = _service.get_entry(run_id)
    except ReceiptChainNotFoundError:
        raise HTTPException(status_code=404, detail="chain entry not found")
    return _entry_to_dict(entry)
