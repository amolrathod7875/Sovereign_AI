"""Judge Mode API.

Read-only evidence aggregation. No mutations.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from judge.service import JudgeService

logger = logging.getLogger(__name__)
router = APIRouter()
_service = JudgeService()


@router.get("/overview")
async def get_overview() -> Dict[str, Any]:
    return await _service.get_overview()


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> Dict[str, Any]:
    detail = _service.get_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="run not found")
    return detail


@router.get("/flagship")
async def get_flagship() -> Dict[str, Any]:
    data, _ = _service._get_flagship()
    return data


@router.get("/evaluation")
async def get_evaluation() -> Dict[str, Any]:
    data, _ = _service._get_evaluation()
    return data
