"""FastAPI integration for the Phase 4 Sovereign AI maintenance agent.

Exposes:
  POST /api/agent/run          -> run the agent for a task
  GET  /api/agent/runs/{id}    -> fetch a stored run result

The agent package is imported lazily inside the handlers so the (heavy) local
retriever/model is only loaded on first use and the app can boot without it.
"""
import logging
import uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

_RUNS: Dict[str, Any] = {}


class AgentRunRequest(BaseModel):
    task: str
    asset_tag: str = "R-1001"


class AgentRunResponse(BaseModel):
    run_id: str
    status: str
    decision: Optional[str] = None
    approval_required: bool = False
    findings: list = []
    artifacts: list = []
    evidence: list = []


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(req: AgentRunRequest):
    from agent.run import run_agent_task

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    try:
        result = run_agent_task(
            req.task, asset_tag=req.asset_tag, run_id=run_id,
            artifact_filename=f"R-1001_api_{run_id}.docx",
        )
    except Exception as e:  # surface failures clearly
        logger.error("agent run failed: %s", e)
        raise HTTPException(status_code=500, detail=f"agent run failed: {e}")

    _RUNS[run_id] = result
    return AgentRunResponse(
        run_id=result["run_id"],
        status=result["status"],
        decision=result.get("decision"),
        approval_required=result.get("approval_required", False),
        findings=result.get("findings", []),
        artifacts=result.get("artifacts", []),
        evidence=result.get("evidence", []),
    )


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    result = _RUNS.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return result
