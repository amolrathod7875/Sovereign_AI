"""M6 unified memory-aware dynamic context builder.

Orchestrates:
  * M3 conversation context (summary + recent history)
  * M5 semantic personal/conversation memory retrieval
  * model message assembly with precedence

Does NOT:
  * create/update/deactivate memory
  * modify RAG retrieval queries
  * trigger memory extraction
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from app.config import settings
from app.context.budget import estimate_tokens
from app.context.builder import build_conversation_context
from app.context.schemas import (
    ConversationContext,
    ConversationContextUsage,
    MemoryContext,
    MemoryContextItem,
    UnifiedContext,
    UnifiedContextUsage,
)
from app.context.access import validate_conversation_access
from app.identity.principal import Principal
from app.memory.search import MemorySemanticSearch, MemorySearchResponse
from app.storage.postgres import Message, async_session
from app.memory.normalization import normalize_memory_content

logger = logging.getLogger(__name__)

_GENERAL_SYSTEM_INSTRUCTION = (
    "You are Sovereign AI, a local on-premise assistant.\n"
    "Use the provided context layers in precedence order:\n"
    "1. Current user request (highest priority; overrides all other context).\n"
    "2. Retrieved local RAG evidence (for organizational/industrial factual claims).\n"
    "3. Recent same-conversation messages (freshest dialogue context).\n"
    "4. Conversation summary (earlier conversation overview).\n"
    "5. Long-term durable memory about the user or current conversation (context only, not higher-priority instruction).\n"
    "Current user request overrides conflicting memory, summary, or history.\n"
    "Explicit relevant USER_PREFERENCE memory may be honored when the current request does not conflict.\n"
    "Memory is NOT organizational evidence. Do not claim memory supports pump specifications, plant facts, vendor facts, equipment status, or company policy.\n"
    "Do not invent evidence that was not supplied."
)

_RAG_SYSTEM_INSTRUCTION = (
    "You are Sovereign AI. Answer organizational, product, asset, plant, engineering, or company factual claims using ONLY the supplied local RAG evidence.\n"
    "Conversation history, summary, and long-term memory may be used for user preferences, continuity, and reference resolution, but they are NOT authoritative organizational evidence.\n"
    "If memory conflicts with supplied RAG evidence on an organizational fact, use the RAG evidence.\n"
    "Current user request overrides conflicting historical preference or context.\n"
    "Do not invent evidence that was not supplied."
)

_MEMORY_BLOCK_HEADER = (
    "[Long-term user memory context.\n"
    "Derived from prior user conversations.\n"
    "Use only when relevant to the current request.\n"
    "Not authoritative organizational evidence.\n"
    "Current user request overrides conflicting memory.\n"
    "Memory items below are historical context only.]\n"
)


def _normalize(text: str) -> str:
    try:
        return normalize_memory_content(text)
    except Exception:
        return text.strip().lower()


async def _build_memory_context(
    principal: Principal,
    query: str,
    conversation_id: Optional[str],
    unified_ctx: ConversationContext,
) -> MemoryContext:
    ctx = MemoryContext(
        used=False,
        retrieval_attempted=False,
        available=False,
        reason="not_attempted",
    )

    remaining = settings.UNIFIED_CONTEXT_TOKEN_BUDGET - unified_ctx.estimated_tokens
    if remaining <= 0:
        ctx.reason = "no_budget_remaining"
        return ctx

    allowed_memory_budget = min(settings.MEMORY_CONTEXT_TOKEN_BUDGET, max(0, remaining))

    search = None
    try:
        ctx.retrieval_attempted = True
        search = MemorySemanticSearch()
        response = await search.search_memories(
            principal=principal,
            query=query,
            conversation_id=conversation_id,
            top_k=settings.MEMORY_CONTEXT_TOP_K,
        )
    except Exception as exc:
        logger.warning("Memory search failed (non-fatal): %s", exc)
        ctx.available = False
        ctx.reason = "memory_index_unavailable"
        return ctx
    finally:
        if search is not None:
            try:
                await search.close()
            except Exception:
                pass

    if not response.results:
        ctx.available = True
        ctx.reason = "no_relevant_memories"
        return ctx

    ctx.available = True
    ctx.candidate_count = response.returned_count

    recent_texts: List[str] = []
    summary_text = ""
    if unified_ctx.recent_messages:
        recent_texts = [_normalize(m.content) for m in unified_ctx.recent_messages if m.content]
    if unified_ctx.summary and unified_ctx.summary.text:
        summary_text = _normalize(unified_ctx.summary.text)
    query_normalized = _normalize(query)

    eligible: List[MemoryContextItem] = []
    for r in response.results:
        if r.semantic_score < settings.MEMORY_CONTEXT_MIN_SEMANTIC_SCORE:
            ctx.skipped_threshold += 1
            continue
        tokens = estimate_tokens(r.content)
        if tokens > allowed_memory_budget:
            ctx.skipped_over_budget += 1
            continue
        norm = _normalize(r.content)
        if norm and norm == query_normalized:
            ctx.skipped_duplicate += 1
            continue
        if recent_texts and norm:
            if any(norm == rt for rt in recent_texts):
                ctx.skipped_duplicate += 1
                continue
        if summary_text and norm and norm == summary_text:
            ctx.skipped_duplicate += 1
            continue
        eligible.append(
            MemoryContextItem(
                memory_id=r.memory_id,
                content=r.content,
                scope=r.scope,
                memory_type=r.memory_type,
                semantic_score=r.semantic_score,
                importance=r.importance,
                confidence=r.confidence,
                estimated_tokens=tokens,
                conversation_id=r.conversation_id,
                user_id=r.user_id,
                version=r.version,
                updated_at=r.updated_at,
            )
        )

    ctx.eligible_count = len(eligible)
    selected: List[MemoryContextItem] = []
    token_total = 0
    for item in eligible:
        if token_total + item.estimated_tokens > allowed_memory_budget and selected:
            ctx.truncated = True
            break
        selected.append(item)
        token_total += item.estimated_tokens

    ctx.items = selected
    ctx.included_count = len(selected)
    ctx.estimated_tokens = token_total
    ctx.used = ctx.included_count > 0
    ctx.reason = "memory_used" if ctx.used else "no_eligible_memories"
    ctx.retrieval_mode = response.retrieval_mode
    ctx.min_semantic_score = settings.MEMORY_CONTEXT_MIN_SEMANTIC_SCORE
    ctx.memory_ids = [i.memory_id for i in selected]
    ctx.scopes = list({i.scope for i in selected})
    return ctx


def _memory_block(mem_ctx: MemoryContext) -> Optional[str]:
    if not mem_ctx.items:
        return None
    lines = [_MEMORY_BLOCK_HEADER]
    for item in mem_ctx.items:
        lines.append(f"- {item.scope} | {item.memory_type}: {item.content}")
    return "\n".join(lines)


def _model_messages(
    task: str,
    conversation_ctx: ConversationContext,
    memory_ctx: MemoryContext,
    use_rag: bool,
    rag_evidence: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    system = _RAG_SYSTEM_INSTRUCTION if use_rag else _GENERAL_SYSTEM_INSTRUCTION
    messages: List[Dict[str, str]] = [{"role": "system", "content": system}]

    mem_block = _memory_block(memory_ctx)
    if mem_block:
        messages.append({"role": "assistant", "content": mem_block})

    if conversation_ctx.summary and conversation_ctx.summary.text:
        messages.append({
            "role": "assistant",
            "content": "[Conversation summary derived from earlier visible messages. Context only; not authoritative organizational evidence.]\n" + conversation_ctx.summary.text,
        })

    for m in conversation_ctx.recent_messages:
        messages.append({"role": m.role, "content": m.content})

    if use_rag and rag_evidence:
        evidence_block = "\n".join(f"- {e}" for e in rag_evidence) or "(no retrieved evidence)"
        messages.append({
            "role": "assistant",
            "content": "Local evidence:\n" + evidence_block,
        })

    messages.append({"role": "user", "content": task})
    return messages


async def build_unified_context(
    principal: Principal,
    task: str,
    conversation_id: Optional[str] = None,
    current_message_id: Optional[str] = None,
    use_rag: bool = False,
) -> Tuple[UnifiedContext, UnifiedContextUsage]:
    if conversation_id is not None:
        async with async_session() as session:
            conv = await validate_conversation_access(session, principal, conversation_id)
        if conv is None:
            # Match existing M3/M2 behavior of raising on foreign conversation
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Conversation not found")

    conversation_ctx, conversation_usage = await build_conversation_context(
        principal=principal,
        conversation_id=conversation_id,
        current_message_id=current_message_id,
    )
    memory_ctx = await _build_memory_context(
        principal=principal,
        query=task,
        conversation_id=conversation_id,
        unified_ctx=conversation_ctx,
    )

    rag_evidence_texts: Optional[List[str]] = None
    if use_rag:
        try:
            from agent.tools.search_kb import search_knowledge_base
            hits = search_knowledge_base(task, top_k=6)
            rag_evidence_texts = [(h.get("text") or "")[:600] for h in hits]
        except Exception:
            rag_evidence_texts = []

    model_messages = _model_messages(
        task=task,
        conversation_ctx=conversation_ctx,
        memory_ctx=memory_ctx,
        use_rag=use_rag,
        rag_evidence=rag_evidence_texts,
    )

    unified = UnifiedContext(
        conversation_id=conversation_id,
        memory_context=memory_ctx,
        conversation_context=conversation_ctx,
        model_messages=model_messages,
        task=task,
        use_rag=use_rag,
    )

    usage = UnifiedContextUsage(
        unified_context_budget=settings.UNIFIED_CONTEXT_TOKEN_BUDGET,
        estimated_history_tokens=conversation_ctx.estimated_tokens,
        estimated_memory_tokens=memory_ctx.estimated_tokens,
        estimated_unified_tokens=conversation_ctx.estimated_tokens + memory_ctx.estimated_tokens,
        budget_remaining=settings.UNIFIED_CONTEXT_TOKEN_BUDGET - (conversation_ctx.estimated_tokens + memory_ctx.estimated_tokens),
        # conversation passthrough
        conversation_id=conversation_usage.conversation_id,
        history_used=conversation_usage.history_used,
        messages_considered=conversation_usage.messages_considered,
        messages_included=conversation_usage.messages_included,
        truncated=conversation_usage.truncated,
        source=conversation_usage.source,
        reason=conversation_usage.reason,
        summary_available=conversation_usage.summary_available,
        summary_used=conversation_usage.summary_used,
        summary_refreshed=conversation_usage.summary_refreshed,
        summary_version=conversation_usage.summary_version,
        summarized_through_sequence_no=conversation_usage.summarized_through_sequence_no,
        summary_estimated_tokens=conversation_usage.summary_estimated_tokens,
        recent_messages_included=conversation_usage.recent_messages_included,
        estimated_recent_tokens=conversation_usage.estimated_recent_tokens,
        compression_active=conversation_usage.compression_active,
        # memory passthrough
        memory_used=memory_ctx.used,
        memory_available=memory_ctx.available,
        memory_retrieval_attempted=memory_ctx.retrieval_attempted,
        memory_candidate_count=memory_ctx.candidate_count,
        memory_eligible_count=memory_ctx.eligible_count,
        memory_included_count=memory_ctx.included_count,
        memory_estimated_tokens=memory_ctx.estimated_tokens,
        memory_truncated=memory_ctx.truncated,
        memory_ids=memory_ctx.memory_ids,
        memory_scopes=memory_ctx.scopes,
        memory_retrieval_mode=memory_ctx.retrieval_mode,
        memory_reason=memory_ctx.reason,
        memory_min_score=memory_ctx.min_semantic_score,
    )
    return unified, usage
