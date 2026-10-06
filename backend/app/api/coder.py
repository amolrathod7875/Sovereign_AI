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
import time
import uuid
from typing import Dict, Any, List, Optional
from httpx import ConnectError

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.schemas import RoutingDecision
from app.conversations.service import persist_assistant_message
from app.storage.postgres import async_session
from app.identity.principal import Principal, get_current_principal_dep
from agent.coder.config import CODER_MODEL_TIMEOUT, CODER_ENDPOINT
from app.models.client import ModelBusyError

logger = logging.getLogger(__name__)
router = APIRouter()

_RUNS: Dict[str, Any] = {}

# End-to-end deadline for the complete coder workflow.
# Allows multiple model calls + test iterations while preventing indefinite hangs.
CODER_DEADLINE = max(CODER_MODEL_TIMEOUT * 3, 900)  # at least 15 minutes


class CoderRunRequest(BaseModel):
    task: str
    conversation_id: Optional[str] = None


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
    response_time_seconds: Optional[float] = None
    model_performance: Optional[Dict[str, Any]] = None
    assistant_message_id: Optional[str] = None


@router.post("/run", response_model=CoderRunResponse)
async def run_coder(req: CoderRunRequest, principal: Principal = Depends(get_current_principal_dep)):
    from agent.coder.run import run_coder_task

    if not (req.task or "").strip():
        raise HTTPException(status_code=422, detail="task must not be empty")

    request_started = time.perf_counter()
    run_id = f"coder_{uuid.uuid4().hex[:12]}"
    try:
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
    except ConnectError as e:
        logger.error("coder connection failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail=(
                f"Local coder model (Qwen2.5-Coder) is not reachable on "
                f"{CODER_ENDPOINT}. Start it with "
                f"'python scripts/serve_model.py --model-id qwen-coder --port 8002'. "
                f"Connection error: {e}"
            ),
        )
    except ModelBusyError as e:
        logger.error("coder model busy: %s", e)
        raise HTTPException(
            status_code=429,
            detail=(
                "Local GPU inference capacity is busy. Try again shortly."
            ),
            headers={"Retry-After": "5"},
        )
    except OSError as e:
        logger.error("coder transport failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail=(
                f"Local coder model (Qwen2.5-Coder) is not reachable on "
                f"{CODER_ENDPOINT}. Start it with "
                f"'python scripts/serve_model.py --model-id qwen-coder --port 8002'. "
                f"Transport error: {e}"
            ),
        )
    except Exception as e:
        logger.error("coder run failed: %s", e)
        raise HTTPException(status_code=500, detail=f"coder run failed: {e}")

    _RUNS[run_id] = result
    fr = result.get("final_result") or {}
    routing = result.get("routing")
    if isinstance(routing, dict) and routing.get("error"):
        routing = None

    response_time_seconds = round(time.perf_counter() - request_started, 3)

    response = CoderRunResponse(
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
        response_time_seconds=response_time_seconds,
        model_performance=result.get("model_performance"),
    )

    assistant_message_id: Optional[str] = None
    if req.conversation_id:
        try:
            async with async_session() as session:
                assistant = await persist_assistant_message(
                    session,
                    conversation_id=req.conversation_id,
                    organization_id=principal.organization_id,
                    principal=principal,
                    content=result.get("reasoning_summary") or result.get("decision"),
                    status=response.status,
                    mode="coding",
                    task_type=(result.get("routing") or {}).get("task_type") if isinstance(result.get("routing"), dict) else None,
                    routing_model=(result.get("routing") or {}).get("selected_model") if isinstance(result.get("routing"), dict) else None,
                    actual_model=(result.get("routing") or {}).get("selected_model") if isinstance(result.get("routing"), dict) else None,
                    rag_used=False,
                    external_calls=response.external_calls,
                    response_time_seconds=response.response_time_seconds,
                    model_inference_seconds=(response.model_performance or {}).get("inference_seconds"),
                    tokens_per_second=(response.model_performance or {}).get("tokens_per_second"),
                    prompt_tokens=(response.model_performance or {}).get("prompt_tokens"),
                    completion_tokens=(response.model_performance or {}).get("completion_tokens"),
                    total_tokens=(response.model_performance or {}).get("total_tokens"),
                    display_payload={
                        "files": result.get("files"),
                        "file_contents": result.get("file_contents"),
                        "test_output": result.get("test_output") or fr.get("test_output"),
                        "execution_trace": result.get("trace"),
                        "errors": result.get("errors"),
                    },
                    idempotency_key=run_id,
                )
                assistant_message_id = assistant.id
        except Exception:
            logger.warning("coder assistant persistence failed", exc_info=True)

    out = response.model_dump()
    if assistant_message_id:
        out["assistant_message_id"] = assistant_message_id
    return out


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
