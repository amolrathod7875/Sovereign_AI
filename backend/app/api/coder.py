"""FastAPI integration for the Phase 5A local coding agent.

Exposes:
  POST /api/coder/run        -> run the coding agent for a task
  GET  /api/coder/runs/{id}  -> fetch a stored run result
"""
import asyncio
import logging
import uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

_RUNS: Dict[str, Any] = {}


class CoderRunRequest(BaseModel):
    task: str


@router.post("/run")
async def run_coder(req: CoderRunRequest):
    from agent.coder.run import run_coder_task

    run_id = f"coder_{uuid.uuid4().hex[:12]}"
    try:
        # The model runs in a thread so we never block the event loop.
        result = await asyncio.to_thread(run_coder_task, req.task, run_id)
    except Exception as e:  # surface failures clearly
        logger.error("coder run failed: %s", e)
        raise HTTPException(status_code=500, detail=f"coder run failed: {e}")

    _RUNS[run_id] = result
    fr = result.get("final_result") or {}
    return {
        "run_id": run_id,
        "status": result.get("status"),
        "files": result.get("files", []),
        "tests": fr.get("test_output"),
        "iterations": fr.get("iterations", 0),
        "execution_trace": result.get("execution_trace", []),
    }


@router.get("/runs/{run_id}")
async def get_coder_run(run_id: str):
    result = _RUNS.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return result
