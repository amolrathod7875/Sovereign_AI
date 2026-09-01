"""FastAPI integration for the Phase 5A local coding agent.

Exposes:
  POST /api/coder/run        -> run the coding agent for a task
  GET  /api/coder/runs       -> list runs held in this process
  GET  /api/coder/runs/{id}  -> fetch a stored run result

Phase 6 change (integration only — the coding agent itself is untouched): the
response now includes the generated file contents, the routing decision, the
sandbox/test output and the measured external-call count, so the UI can show the
real produced code and verification result instead of a second round-trip.
"""
import asyncio
import logging
import uuid
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas import RoutingDecision
from agent.coder.config import CODER_MODEL_TIMEOUT

logger = logging.getLogger(__name__)
router = APIRouter()

_RUNS: Dict[str, Any] = {}

# End-to-end deadline for the complete coder workflow.
# Allows multiple model calls + test iterations while preventing indefinite hangs.
CODER_DEADLINE = max(CODER_MODEL_TIMEOUT * 3, 900)  # at least 15 minutes


class CoderRunRequest(BaseModel):
    task: str


class CoderRunResponse(BaseModel):
    run_id: str
    status: str
    files: List[str] = []
    file_contents: Dict[str, str] = {}
    test_output: Dict[str, Any] = {}
    test_command: str = ""
    iterations: int = 0
    failure_analysis: str = ""
    workspace: str = ""
    execution_trace: List[Dict[str, Any]] = []
    errors: List[Any] = []
    external_calls: int = 0
    routing: RoutingDecision | None = None


@router.post("/run", response_model=CoderRunResponse)
async def run_coder(req: CoderRunRequest):
    from agent.coder.run import run_coder_task

    if not (req.task or "").strip():
        raise HTTPException(status_code=422, detail="task must not be empty")

    run_id = f"coder_{uuid.uuid4().hex[:12]}"
    try:
        # The model runs in a thread so we never block the event loop.
        # Application-level deadline prevents indefinite hangs on CPU-only inference.
        result = await asyncio.wait_for(
            asyncio.to_thread(run_coder_task, req.task, run_id),
            timeout=CODER_DEADLINE,
        )
    except asyncio.TimeoutError:
        logger.error("coder run timed out after %ds: %s", CODER_DEADLINE, req.task[:100])
        raise HTTPException(
            status_code=504,
            detail=(
                f"Coder workflow exceeded {CODER_DEADLINE}s deadline. "
                "The local model may be overloaded or the task too complex. "
                "Try a simpler task or check the model server."
            ),
        )
    except Exception as e:  # surface failures clearly
        logger.error("coder run failed: %s", e)
        raise HTTPException(status_code=500, detail=f"coder run failed: {e}")

    _RUNS[run_id] = result
    fr = result.get("final_result") or {}
    routing = result.get("routing")
    if isinstance(routing, dict) and routing.get("error"):
        routing = None

    return CoderRunResponse(
        run_id=run_id,
        status=result.get("status", "UNKNOWN"),
        files=result.get("files", []),
        file_contents=result.get("file_contents", {}) or {},
        test_output=result.get("test_output") or fr.get("test_output") or {},
        test_command=result.get("test_command", "") or "",
        iterations=fr.get("iterations", result.get("iteration", 0)) or 0,
        failure_analysis=result.get("failure_analysis", "") or "",
        workspace=result.get("workspace", "") or "",
        execution_trace=result.get("trace", []) or [],
        errors=result.get("errors", []) or [],
        external_calls=result.get("external_calls", 0) or 0,
        routing=routing,
    )


@router.get("/runs")
async def list_coder_runs(limit: int = 50) -> List[Dict[str, Any]]:
    items = [
        {
            "run_id": r.get("run_id"),
            "status": r.get("status"),
            "files": r.get("files", []),
            "external_calls": r.get("external_calls", 0),
            "selected_model": (r.get("routing") or {}).get("selected_model"),
            "task_type": (r.get("routing") or {}).get("task_type"),
        }
        for r in _RUNS.values()
    ]
    return items[-limit:][::-1]


@router.get("/runs/{run_id}")
async def get_coder_run(run_id: str):
    result = _RUNS.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return result
