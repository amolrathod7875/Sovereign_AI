"""Chat surface.

NOTE (Phase 6 integration fix): this module previously also declared
``POST /agent/run`` and ``GET /agent/run/{task_id}/stream``, which were mounted at
``/api`` and therefore resolved to ``/api/agent/run`` BEFORE the authoritative
``app.api.agent`` router (mounted at ``/api/agent``). Because FastAPI matches
routes in registration order, every call to ``POST /api/agent/run`` was served by
``app.agents.graph.run_agent`` — the dead/placeholder duplicate documented in
``reports/phase5d_architecture.md`` §2 — instead of the authoritative LangGraph
agent in ``backend/agent``.

Those two shadowing routes have been removed so ``/api/agent/run`` reaches the
authoritative agent (``app.api.agent`` -> ``agent.run.run_agent_task``). No new
agent, API or streaming protocol was introduced.
"""
from fastapi import APIRouter
import logging

from app.schemas import ChatRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    """Deprecated placeholder kept for backward compatibility.

    The real execution surface is ``POST /api/agent/run`` (maintenance /
    knowledge / multimodal), ``POST /api/coder/run`` (coding) and
    ``POST /api/vision/analyze`` (vision), selected by ``POST /api/models/route``.
    """
    return {
        "message": "Deprecated. Use POST /api/agent/run, /api/coder/run or /api/vision/analyze.",
        "routing_endpoint": "/api/models/route",
        "streaming": False,
    }
