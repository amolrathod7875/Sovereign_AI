from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ContextMessage:
    role: str
    content: str
    message_id: str
    sequence_no: int


@dataclass
class ConversationSummaryContext:
    text: str
    summarized_through_sequence_no: int
    estimated_tokens: int
    version: int
    model_id: Optional[str] = None


@dataclass
class ConversationContext:
    conversation_id: str
    summary: Optional[ConversationSummaryContext] = None
    recent_messages: List[ContextMessage] = field(default_factory=list)
    messages_considered: int = 0
    messages_included: int = 0
    truncated: bool = False
    estimated_tokens: int = 0
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
    # M3 summary fields
    summary_available: bool = False
    summary_used: bool = False
    summary_refreshed: bool = False
    summary_version: Optional[int] = None
    summarized_through_sequence_no: Optional[int] = None
    summary_estimated_tokens: Optional[int] = None
    recent_messages_included: Optional[int] = None
    estimated_recent_tokens: Optional[int] = None
    compression_active: bool = False
