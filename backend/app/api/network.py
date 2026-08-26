from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
import asyncio
import json
from typing import List

from app.schemas import NetworkEvent

router = APIRouter()

_events: List[NetworkEvent] = []


@router.get("/monitor")
async def network_monitor():
    async def event_generator():
        while True:
            if _events:
                event = _events.pop(0)
                yield {
                    "event": "connection_attempt",
                    "data": json.dumps(event.model_dump()),
                }
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/events")
async def get_network_events(limit: int = 100) -> List[NetworkEvent]:
    return _events[-limit:]


def add_network_event(event: NetworkEvent):
    _events.append(event)
    if len(_events) > 1000:
        _events.pop(0)
