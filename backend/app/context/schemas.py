from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ContextMessage:
    role: str
    content: str
    message_id: str
    sequence_no: int


@dataclass
class ConversationContext:
    conversation_id: str
    recent_messages: List[ContextMessage]
    messages_considered: int
    messages_included: int
    truncated: bool
    estimated_tokens: int
    source: str = "postgresql_history"


@dataclass
class ConversationContextUsage:
    conversation_id: Optional[str]
    history_used: bool
    messages_considered: int
    messages_included: int
    estimated_history_tokens: int
    truncated: bool
    source: str = "none"
    reason: Optional[str] = None
