"""FastAPI integration for the authoritative Sovereign AI maintenance agent.

Exposes:
  POST /api/agent/run          -> run the agent for a task
  GET  /api/agent/runs         -> list runs held in this process
  GET  /api/agent/runs/{id}    -> fetch a stored run result

The agent package is imported lazily inside the handlers so the (heavy) local
retriever/model is only loaded on first use and the app can boot without it.

Phase 6 changes (integration only — the agent itself is untouched):
  * the blocking graph invocation runs in a worker thread so a long CPU-bound run
    no longer freezes the event loop (status polling / uploads stay responsive);
  * the response surfaces the metadata the run already produces (reasoning summary,
    routing, trace, calculations, verification, errors) so the UI can display real
    execution facts instead of issuing a second request or inventing them.
"""
import asyncio
import logging
import uuid
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas import RoutingDecision

logger = logging.getLogger(__name__)
router = APIRouter()

_RUNS: Dict[str, Any] = {}


class AgentRunRequest(BaseModel):
    task: str
    asset_tag: str = "R-1001"
    image_path: Optional[str] = None
    analysis_type: str = "general"


class AgentRunResponse(BaseModel):
    run_id: str
    status: str
    decision: Optional[str] = None
    reasoning_summary: Optional[str] = None
    approval_required: bool = False
    required_actions: list = []
    supporting_evidence: list = []
    findings: list = []
    artifacts: list = []
    evidence: list = []
    vision_evidence: list = []
    vision_tags: list = []
    calculations_summary: dict = {}
    verification: dict = {}
    trace: list = []
    errors: list = []
    image_path: Optional[str] = None
    analysis_type: str = "general"
    external_calls: int = 0
    routing: Optional[RoutingDecision] = None


def _to_response(result: Dict[str, Any]) -> AgentRunResponse:
    routing = result.get("routing")
    # `route()` failures are recorded as {"error": ...}; do not fake a decision.
    if isinstance(routing, dict) and routing.get("error"):
        routing = None
    return AgentRunResponse(
        run_id=result["run_id"],
        status=result["status"],
        decision=result.get("decision"),
        reasoning_summary=result.get("reasoning_summary"),
        approval_required=result.get("approval_required", False),
        required_actions=result.get("required_actions", []),
        supporting_evidence=result.get("supporting_evidence", []),
        findings=result.get("findings", []),
        artifacts=result.get("artifacts", []),
        evidence=result.get("evidence", []),
        vision_evidence=result.get("vision_evidence", []),
        vision_tags=result.get("vision_tags", []),
        calculations_summary=result.get("calculations_summary") or {},
        verification=result.get("verification") or {},
        trace=result.get("trace", []),
        errors=result.get("errors", []),
        image_path=result.get("image_path"),
        analysis_type=result.get("analysis_type", "general"),
        external_calls=result.get("external_calls", 0),
        routing=routing,
    )


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(req: AgentRunRequest):
    from agent.run import run_agent_task

    if not (req.task or "").strip():
        raise HTTPException(status_code=422, detail="task must not be empty")

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    try:
        # The graph is synchronous and CPU-bound: keep it off the event loop.
        result = await asyncio.to_thread(
            run_agent_task,
            req.task,
            req.asset_tag,
            run_id,
            f"{req.asset_tag}_api_{run_id}.docx",
            req.image_path,
            req.analysis_type,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # surface failures clearly
        logger.error("agent run failed: %s", e)
        raise HTTPException(status_code=500, detail=f"agent run failed: {e}")

    _RUNS[run_id] = result
    return _to_response(result)


@router.get("/runs")
async def list_runs(limit: int = 50) -> List[Dict[str, Any]]:
    """Runs performed by THIS backend process (in-memory; not a database)."""
    items = [
        {
            "run_id": r.get("run_id"),
            "status": r.get("status"),
            "decision": r.get("decision"),
            "approval_required": r.get("approval_required", False),
            "artifacts": r.get("artifacts", []),
            "external_calls": r.get("external_calls", 0),
            "selected_model": (r.get("routing") or {}).get("selected_model"),
            "task_type": (r.get("routing") or {}).get("task_type"),
        }
        for r in _RUNS.values()
    ]
    return items[-limit:][::-1]


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    result = _RUNS.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return result
