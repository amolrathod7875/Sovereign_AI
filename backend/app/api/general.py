"""General / RAG execution surface.

This is the authoritative local endpoint for non-maintenance, non-coding, non-vision
tasks. It replaces the previous pattern of routing every text task through the
industrial maintenance agent.

POST /api/general/run
  * GENERAL_QA -> local general synthesis only
  * RAG_QA     -> hybrid retrieval + local general synthesis (if available)
"""
from fastapi import APIRouter, HTTPException
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from app.schemas import RoutingDecision
from app.models.router import route, RoutingRequest, NoLocalModelAvailable
from app.models.registry import get_model, is_local_endpoint
from agent.tools.search_kb import search_knowledge_base
from agent.security.netguard import no_network

logger = logging.getLogger(__name__)
router = APIRouter()


class GeneralRunRequest(BaseModel):
    task: str
    asset_tag: Optional[str] = None
    use_rag: bool = False


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


def _try_general_synthesis(task: str, evidence: List[Dict[str, Any]], max_tokens: int = 1024) -> Dict[str, Any]:
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
    try:
        from app.models.client import ModelClient
        ctx = "\n".join(f"- {e.get('text', '')}" for e in evidence[:4]) or "(no retrieved evidence)"
        messages = [
            {"role": "system", "content": "You are Sovereign AI. Answer using ONLY the provided local evidence. If the evidence does not answer the question, state that clearly."},
            {"role": "user", "content": f"Task: {task}\n\nLocal evidence:\n{ctx}"},
        ]
        client = ModelClient("general", endpoint)
        answer = client.generate(messages, max_tokens=max_tokens)
        return {"used": True, "answer": answer}
    except Exception as e:
        return {"used": False, "reason": f"general synthesis failed: {e}", "rag_evidence_count": len(evidence)}


@router.post("/run", response_model=GeneralRunResponse)
async def run_general(req: GeneralRunRequest) -> Dict[str, Any]:
    task = (req.task or "").strip()
    if not task:
        raise HTTPException(status_code=422, detail="task must not be empty")

    try:
        routing = route(RoutingRequest(task=task, asset_tag=req.asset_tag or None)).model_dump()
    except NoLocalModelAvailable as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.warning("routing failed: %s", e)
        routing = {"error": str(e), "selected_model": None, "task_type": "GENERAL_QA", "models_required": [], "requires_rag": False}

    task_type = routing.get("task_type", "GENERAL_QA")
    use_rag = bool(req.use_rag or routing.get("requires_rag"))
    evidence: List[Dict[str, Any]] = []
    rag_used = False
    actual_execution: List[str] = []
    errors: List[str] = []

    with no_network() as guard:
        if use_rag or task_type == "RAG_QA":
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

        synth = _try_general_synthesis(task, evidence)
        if synth.get("used"):
            actual_execution.append("general")
        else:
            reason = synth.get("reason", "general synthesis unavailable")
            errors.append(reason)

    status = "UNAVAILABLE" if not actual_execution else "COMPLETED"
    answer = synth.get("answer") if synth.get("used") else None
    if not answer and not actual_execution:
        answer = None

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
    )
    return response.model_dump()

