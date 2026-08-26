from typing import TypedDict, List, Optional, Dict, Any
from datetime import datetime

from app.schemas import TaskType


class AgentState(TypedDict):
    request_id: str
    user_id: Optional[str]
    conversation_id: Optional[str]
    task_type: Optional[str]
    plan: Optional[List[str]]
    selected_model: Optional[str]
    retrieved_context: Optional[List[Dict]]
    tool_calls: List[Dict]
    observations: List[str]
    artifacts: List[str]
    errors: List[str]
    status: str
    message: str
    attachments: List[str]
    has_image: bool
    steps: List[Dict]
    external_calls: int
    started_at: datetime


def create_initial_state(request_id: str, message: str, attachments: List[str] = None) -> AgentState:
    return AgentState(
        request_id=request_id,
        user_id=None,
        conversation_id=None,
        task_type=None,
        plan=None,
        selected_model=None,
        retrieved_context=None,
        tool_calls=[],
        observations=[],
        artifacts=[],
        errors=[],
        status="PENDING",
        message=message,
        attachments=attachments or [],
        has_image=False,
        steps=[],
        external_calls=0,
        started_at=datetime.utcnow(),
    )
