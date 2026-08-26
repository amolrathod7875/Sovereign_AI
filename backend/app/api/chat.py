from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse
import asyncio
import json
import logging

from app.schemas import AgentRunRequest, ChatRequest, ChatResponse, ChatMessage

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    return {"message": "Chat endpoint - use /agent/run for full workflow"}


@router.post("/agent/run")
async def agent_run(request: AgentRunRequest):
    from app.agents.graph import run_agent

    task_id = f"task_{asyncio.get_event_loop().time().__int__()}"
    result = await run_agent(request, task_id)
    return result


@router.get("/agent/run/{task_id}/stream")
async def agent_run_stream(task_id: str):
    from app.agents.graph import agent_stream

    async def event_generator():
        async for event in agent_stream(task_id):
            yield {
                "event": event.get("type", "message"),
                "data": json.dumps(event),
            }

    return EventSourceResponse(event_generator())
