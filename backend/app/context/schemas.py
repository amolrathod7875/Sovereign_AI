from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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


# ---------------------------------------------------------------------------
# M6 unified memory-aware context
# ---------------------------------------------------------------------------
@dataclass
class MemoryContextItem:
    memory_id: str
    content: str
    scope: str
    memory_type: str
    semantic_score: float
    importance: float
    confidence: float
    estimated_tokens: int
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    version: Optional[int] = None
    updated_at: Optional[str] = None
    skip_reason: Optional[str] = None


@dataclass
class MemoryContext:
    used: bool
    retrieval_attempted: bool
    available: bool
    reason: Optional[str] = None
    candidate_count: int = 0
    eligible_count: int = 0
    included_count: int = 0
    estimated_tokens: int = 0
    truncated: bool = False
    skipped_over_budget: int = 0
    skipped_duplicate: int = 0
    skipped_threshold: int = 0
    memory_ids: List[str] = field(default_factory=list)
    scopes: List[str] = field(default_factory=list)
    retrieval_mode: str = "semantic_memory"
    min_semantic_score: float = 0.0
    items: List[MemoryContextItem] = field(default_factory=list)


@dataclass
class UnifiedContext:
    conversation_id: Optional[str]
    memory_context: MemoryContext
    conversation_context: ConversationContext
    model_messages: List[Dict[str, str]] = field(default_factory=list)
    task: str = ""
    use_rag: bool = False


@dataclass
class UnifiedContextUsage:
    unified_context_budget: int = 0
    estimated_history_tokens: int = 0
    estimated_memory_tokens: int = 0
    estimated_unified_tokens: int = 0
    budget_remaining: int = 0
    # Conversation usage passthrough
    conversation_id: Optional[str] = None
    history_used: bool = False
    messages_considered: int = 0
    messages_included: int = 0
    truncated: bool = False
    source: str = "none"
    reason: Optional[str] = None
    summary_available: bool = False
    summary_used: bool = False
    summary_refreshed: bool = False
    summary_version: Optional[int] = None
    summarized_through_sequence_no: Optional[int] = None
    summary_estimated_tokens: Optional[int] = None
    recent_messages_included: Optional[int] = None
    estimated_recent_tokens: Optional[int] = None
    compression_active: bool = False
    # Memory usage passthrough
    memory_used: bool = False
    memory_available: bool = False
    memory_retrieval_attempted: bool = False
    memory_candidate_count: int = 0
    memory_eligible_count: int = 0
    memory_included_count: int = 0
    memory_estimated_tokens: int = 0
    memory_truncated: bool = False
    memory_ids: List[str] = field(default_factory=list)
    memory_scopes: List[str] = field(default_factory=list)
    memory_retrieval_mode: str = "semantic_memory"
    memory_reason: Optional[str] = None
    memory_min_score: float = 0.0
