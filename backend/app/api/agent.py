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
import time
import uuid
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.schemas import RoutingDecision
from app.conversations.service import persist_assistant_message
from app.storage.postgres import async_session
from app.identity.principal import Principal, get_current_principal_dep
from governance.approval import ApprovalService, ApprovalConflictError, ArtifactIntegrityError

logger = logging.getLogger(__name__)
router = APIRouter()

_RUNS: Dict[str, Any] = {}


class AgentRunRequest(BaseModel):
    task: str
    asset_tag: str = "R-1001"
    image_path: Optional[str] = None
    analysis_type: str = "general"
    conversation_id: Optional[str] = None
    current_message_id: Optional[str] = None


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
    human_review_status: Optional[str] = None
    approval_record_available: bool = False
    response_time_seconds: Optional[float] = None
    model_performance: Optional[Dict[str, Any]] = None
    assistant_message_id: Optional[str] = None


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
async def run_agent(req: AgentRunRequest, principal: Principal = Depends(get_current_principal_dep)):
    from agent.run import run_agent_task

    if not (req.task or "").strip():
        raise HTTPException(status_code=422, detail="task must not be empty")

    request_started = time.perf_counter()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    try:
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
    except Exception as e:
        logger.error("agent run failed: %s", e)
        raise HTTPException(status_code=500, detail=f"agent run failed: {e}")

    _RUNS[run_id] = result

    human_review_status = "NOT_REQUIRED"
    approval_record_available = False
    if result.get("approval_required"):
        try:
            approval_svc = ApprovalService()
            record = approval_svc.create_pending_from_run(result)
            if record is not None:
                human_review_status = record.status
                approval_record_available = True
            else:
                human_review_status = "NOT_REQUIRED"
                approval_record_available = False
        except ApprovalConflictError as e:
            logger.error("approval registration conflict: %s", e)
            raise HTTPException(status_code=422, detail=f"approval registration failed: {e}")
        except ArtifactIntegrityError as e:
            logger.error("approval artifact integrity error: %s", e)
            raise HTTPException(status_code=409, detail=f"approval registration failed: {e}")
        except Exception as e:
            logger.error("approval registration failed: %s", e)
            raise HTTPException(status_code=500, detail=f"approval registration failed: {e}")

    resp = _to_response(result)
    resp.human_review_status = human_review_status
    resp.approval_record_available = approval_record_available
    resp.response_time_seconds = round(time.perf_counter() - request_started, 3)
    resp.model_performance = None

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
                    status="COMPLETED" if result.get("status") not in (None, "FAILED", "ERROR") else "FAILED",
                    mode="knowledge",
                    task_type=(result.get("routing") or {}).get("task_type") if isinstance(result.get("routing"), dict) else None,
                    routing_model=(result.get("routing") or {}).get("selected_model") if isinstance(result.get("routing"), dict) else None,
                    actual_model="Industrial LangGraph workflow",
                    rag_used=(result.get("routing") or {}).get("requires_rag") if isinstance(result.get("routing"), dict) else None,
                    tools_used="Local tools" if (result.get("routing") or {}).get("requires_tools") else None,
                    local_execution=(result.get("routing") or {}).get("all_local") if isinstance(result.get("routing"), dict) else None,
                    external_calls=result.get("external_calls", 0),
                    response_time_seconds=resp.response_time_seconds,
                    display_payload={
                        "reasoning_summary": result.get("reasoning_summary"),
                        "decision": result.get("decision"),
                        "evidence": result.get("evidence"),
                        "vision_evidence": result.get("vision_evidence"),
                        "vision_tags": result.get("vision_tags"),
                        "artifacts": result.get("artifacts"),
                        "errors": result.get("errors"),
                        "trace": result.get("trace"),
                    },
                    idempotency_key=run_id,
                )
                assistant_message_id = assistant.id
        except Exception:
            logger.warning("agent assistant persistence failed", exc_info=True)

    out = resp.model_dump()
    if assistant_message_id:
        out["assistant_message_id"] = assistant_message_id
    return out


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
