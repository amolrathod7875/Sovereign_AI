"""General / RAG execution surface.

This is the authoritative local endpoint for non-maintenance, non-coding, non-vision
tasks. It replaces the previous pattern of routing every text task through the
industrial maintenance agent.

POST /api/general/run
  * GENERAL_QA -> local general synthesis only
  * RAG_QA     -> hybrid retrieval + local general synthesis (if available)
"""
import time
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Request
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from app.schemas import RoutingDecision
from app.models.router import route, RoutingRequest, NoLocalModelAvailable
from app.models.registry import get_model, is_local_endpoint
from app.identity.principal import get_current_principal, get_current_principal_dep, Principal
from agent.tools.search_kb import search_knowledge_base
from agent.security.netguard import no_network

logger = logging.getLogger(__name__)
router = APIRouter()


class GeneralRunRequest(BaseModel):
    task: str
    asset_tag: Optional[str] = None
    use_rag: bool = False
    conversation_id: Optional[str] = None
    current_message_id: Optional[str] = None


class GeneralRunResponse(BaseModel):
    status: str
    answer: Optional[str] = None
    routing: Dict[str, Any] = {}
    rag_used: bool = False
    evidence: List[Dict[str, Any]] = []
    actual_model_execution: List[str] = []
    external_calls: int = 0
    errors: List[str] = []
    message: Optional[str] = None
    response_time_seconds: Optional[float] = None
    model_performance: Optional[Dict[str, Any]] = None
    conversation_context: Optional[Dict[str, Any]] = None
    memory_context: Optional[Dict[str, Any]] = None
    unified_context: Optional[Dict[str, Any]] = None


async def _try_general_synthesis(
    task: str,
    evidence: List[Dict[str, Any]],
    max_tokens: int = 1024,
    use_rag: bool = False,
    context_messages: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Attempt local general synthesis. Never raises."""
    m = get_model("general")
    if not m:
        return {"used": False, "reason": "general model not registered", "rag_evidence_count": len(evidence)}
    endpoint = m.get("endpoint")
    if not endpoint or not is_local_endpoint(endpoint):
        return {"used": False, "reason": "general endpoint not local/configured", "rag_evidence_count": len(evidence)}
    try:
        import httpx
        with httpx.Client(timeout=3.0) as c:
            ok = c.get(f"{endpoint.rstrip('/')}/models").status_code == 200
    except Exception:
        ok = False
    if not ok:
        return {"used": False, "reason": "general model server not running on this host", "rag_evidence_count": len(evidence)}
    client = None
    try:
        from app.models.client import ModelClient
        if use_rag:
            system = (
                "You are Sovereign AI. Answer using ONLY the supplied local evidence. "
                "If the evidence does not answer the question, state that clearly. "
                "Preceding conversation messages may be used to resolve references and follow-up "
                "questions, but they are NOT authoritative organizational evidence. "
                "Long-term user memory is context only and is NOT organizational evidence."
            )
            ctx = "\n".join(f"- {e.get('text', '')}" for e in evidence[:4]) or "(no retrieved evidence)"
            user = f"Task: {task}\n\nLocal evidence:\n{ctx}"
        else:
            system = (
                "You are Sovereign AI, a local on-premise assistant. "
                "Use the preceding context messages (long-term memory, conversation summary, recent history) to resolve references and follow-up questions. "
                "Long-term user memory is context only and is NOT organizational evidence. "
                "Answer the user's question clearly and accurately. "
                "Current user request overrides conflicting memory, summary, or history. "
                "Do not claim access to evidence that was not provided."
            )
            user = task

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        if context_messages:
            messages.extend(context_messages)
        messages.append({"role": "user", "content": user})

        client = ModelClient("general", endpoint)
        result = await client.generate_with_metrics(messages, max_tokens=max_tokens)
        answer = result["content"]
        return {
            "used": True,
            "answer": answer,
            "usage": result.get("usage"),
            "performance": result.get("performance"),
        }
    except Exception as e:
        return {"used": False, "reason": f"general synthesis failed: {e}", "rag_evidence_count": len(evidence)}
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass


@router.post("/run", response_model=GeneralRunResponse)
async def run_general(
    req: GeneralRunRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal_dep),
) -> Dict[str, Any]:
    task = (req.task or "").strip()
    if not task:
        raise HTTPException(status_code=422, detail="task must not be empty")

    request_started = time.perf_counter()

    unified: Optional[UnifiedContext] = None
    unified_usage: Optional[UnifiedContextUsage] = None
    try:
        from app.context.unified_builder import build_unified_context
        unified, unified_usage = await build_unified_context(
            principal=principal,
            task=task,
            conversation_id=req.conversation_id,
            current_message_id=req.current_message_id,
            use_rag=bool(req.use_rag),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("unified context build failed: %s", e)
        unified = None
        unified_usage = None

    context_messages: List[Dict[str, str]] = []
    if unified and unified.model_messages:
        context_messages = unified.model_messages

    try:
        routing = route(RoutingRequest(task=task, asset_tag=req.asset_tag or None)).model_dump()
    except NoLocalModelAvailable as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.warning("routing failed: %s", e)
        routing = {"error": str(e), "selected_model": None, "task_type": "GENERAL_QA", "models_required": [], "requires_rag": False}

    evidence: List[Dict[str, Any]] = []
    rag_used = False
    actual_execution: List[str] = []
    errors: List[str] = []

    with no_network() as guard:
        if req.use_rag:
            rag_used = True
            try:
                hits = search_knowledge_base(task, asset_tag=req.asset_tag or None, top_k=6)
                evidence = [
                    {
                        "claim": None,
                        "source": h.get("source_file"),
                        "document_type": h.get("document_type"),
                        "confidence": round(float(h.get("score", 0.0)), 3),
                        "text": (h.get("text") or "")[:600],
                        "asset_tag": h.get("asset_tag"),
                        "chunk_id": h.get("chunk_id"),
                        "section": h.get("section"),
                        "retrieval_mode": h.get("retrieval_mode"),
                    }
                    for h in hits
                ]
            except Exception as e:
                errors.append(f"RAG retrieval failed: {e}")
                rag_used = False
            if not evidence:
                rag_used = False

        synth = await _try_general_synthesis(
            task, evidence, use_rag=bool(rag_used), context_messages=context_messages
        )
        if synth.get("used"):
            actual_execution.append("general")
        else:
            reason = synth.get("reason", "general synthesis unavailable")
            errors.append(reason)

    status = "UNAVAILABLE" if not actual_execution else "COMPLETED"
    answer = synth.get("answer") if synth.get("used") else None
    if not answer and not actual_execution:
        answer = None

    response_time_seconds = round(time.perf_counter() - request_started, 3)
    model_performance = synth.get("performance") if synth.get("used") else None

    if unified_usage is None and req.conversation_id:
        unified_usage = type("UnifiedContextUsage", (), {})()
        for name, value in {
            "conversation_id": req.conversation_id,
            "history_used": False,
            "messages_considered": 0,
            "messages_included": 0,
            "estimated_history_tokens": 0,
            "truncated": False,
            "source": "none",
            "reason": "history_unavailable",
            "memory_used": False,
            "memory_available": False,
            "memory_retrieval_attempted": False,
            "memory_candidate_count": 0,
            "memory_eligible_count": 0,
            "memory_included_count": 0,
            "memory_estimated_tokens": 0,
            "memory_truncated": False,
            "memory_ids": [],
            "memory_scopes": [],
            "memory_retrieval_mode": "semantic_memory",
            "memory_reason": "history_unavailable",
            "memory_min_score": 0.0,
        }.items():
            setattr(unified_usage, name, value)
        unified_usage.unified_context_budget = settings.UNIFIED_CONTEXT_TOKEN_BUDGET
        unified_usage.estimated_unified_tokens = 0
        unified_usage.budget_remaining = settings.UNIFIED_CONTEXT_TOKEN_BUDGET

    conversation_context_meta = None
    memory_context_meta = None
    unified_context_meta = None
    if unified_usage is not None:
        conversation_context_meta = {
            "conversation_id": unified_usage.conversation_id,
            "history_used": unified_usage.history_used,
            "messages_considered": unified_usage.messages_considered,
            "messages_included": unified_usage.messages_included,
            "estimated_history_tokens": unified_usage.estimated_history_tokens,
            "truncated": unified_usage.truncated,
            "source": unified_usage.source,
            "reason": unified_usage.reason,
            "summary_available": unified_usage.summary_available,
            "summary_used": unified_usage.summary_used,
            "summary_refreshed": unified_usage.summary_refreshed,
            "summary_version": unified_usage.summary_version,
            "summarized_through_sequence_no": unified_usage.summarized_through_sequence_no,
            "summary_estimated_tokens": unified_usage.summary_estimated_tokens,
            "recent_messages_included": unified_usage.recent_messages_included,
            "estimated_recent_tokens": unified_usage.estimated_recent_tokens,
            "compression_active": unified_usage.compression_active,
        }
        memory_context_meta = {
            "used": unified_usage.memory_used,
            "available": unified_usage.memory_available,
            "retrieval_attempted": unified_usage.memory_retrieval_attempted,
            "candidate_count": unified_usage.memory_candidate_count,
            "eligible_count": unified_usage.memory_eligible_count,
            "included_count": unified_usage.memory_included_count,
            "estimated_tokens": unified_usage.memory_estimated_tokens,
            "truncated": unified_usage.memory_truncated,
            "skipped_over_budget": unified.memory_context.skipped_over_budget if unified else 0,
            "skipped_duplicate": unified.memory_context.skipped_duplicate if unified else 0,
            "skipped_threshold": unified.memory_context.skipped_threshold if unified else 0,
            "memory_ids": unified_usage.memory_ids,
            "scopes": unified_usage.memory_scopes,
            "retrieval_mode": unified_usage.memory_retrieval_mode,
            "reason": unified_usage.memory_reason,
            "min_semantic_score": unified_usage.memory_min_score,
        }
        unified_context_meta = {
            "unified_context_budget": unified_usage.unified_context_budget,
            "estimated_history_tokens": unified_usage.estimated_history_tokens,
            "estimated_memory_tokens": unified_usage.estimated_memory_tokens,
            "estimated_unified_tokens": unified_usage.estimated_unified_tokens,
            "budget_remaining": unified_usage.budget_remaining,
        }

    response = GeneralRunResponse(
        status=status,
        answer=answer,
        routing=routing,
        rag_used=rag_used and len(evidence) > 0,
        evidence=evidence,
        actual_model_execution=actual_execution,
        external_calls=guard.external_calls,
        errors=errors,
        message="General model is not currently available on this host." if status == "UNAVAILABLE" else None,
        response_time_seconds=response_time_seconds,
        model_performance=model_performance,
        conversation_context=conversation_context_meta,
        memory_context=memory_context_meta,
        unified_context=unified_context_meta,
    )
    return response.model_dump()
