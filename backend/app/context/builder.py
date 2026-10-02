from typing import List, Optional, Tuple
from fastapi import HTTPException

from app.context.budget import (
    CONVERSATION_CONTEXT_MAX_MESSAGES,
    CONVERSATION_CONTEXT_TOKEN_BUDGET,
    CONVERSATION_SUMMARY_MAX_TOKENS,
    CONVERSATION_SUMMARY_KEEP_RECENT_MESSAGES,
    estimate_tokens,
)
from app.context.repository import load_conversation_messages
from app.context.schemas import (
    ContextMessage,
    ConversationContext,
    ConversationContextUsage,
    ConversationSummaryContext,
)
from app.identity.principal import Principal
from app.storage.postgres import Message, async_session
from app.context.summarizer import load_summary_for_conversation
from app.context.summary_repository import get_summary


async def build_conversation_context(
    principal: Principal,
    conversation_id: Optional[str],
    current_message_id: Optional[str] = None,
    current_sequence_no: Optional[int] = None,
    max_messages: int = CONVERSATION_CONTEXT_MAX_MESSAGES,
    token_budget: int = CONVERSATION_CONTEXT_TOKEN_BUDGET,
) -> Tuple[ConversationContext, ConversationContextUsage]:
    if not conversation_id or not principal:
        empty = ConversationContext(
            conversation_id=conversation_id or "",
            recent_messages=[],
            messages_considered=0,
            messages_included=0,
            truncated=False,
            estimated_tokens=0,
        )
        usage = ConversationContextUsage(
            conversation_id=conversation_id,
            history_used=False,
            messages_considered=0,
            messages_included=0,
            estimated_history_tokens=0,
            truncated=False,
            source="none",
        )
        return empty, usage

    if async_session is None:
        empty = ConversationContext(
            conversation_id=conversation_id,
            recent_messages=[],
            messages_considered=0,
            messages_included=0,
            truncated=False,
            estimated_tokens=0,
        )
        usage = ConversationContextUsage(
            conversation_id=conversation_id,
            history_used=False,
            messages_considered=0,
            messages_included=0,
            estimated_history_tokens=0,
            truncated=False,
            source="none",
            reason="history_unavailable",
        )
        return empty, usage

    async with async_session() as session:
        before_seq = None
        if current_sequence_no is not None:
            before_seq = current_sequence_no
        elif current_message_id is not None:
            msg = await session.get(Message, current_message_id)
            if msg and msg.conversation_id == conversation_id:
                before_seq = msg.sequence_no

        if before_seq is None:
            empty = ConversationContext(
                conversation_id=conversation_id,
                recent_messages=[],
                messages_considered=0,
                messages_included=0,
                truncated=False,
                estimated_tokens=0,
            )
            usage = ConversationContextUsage(
                conversation_id=conversation_id,
                history_used=False,
                messages_considered=0,
                messages_included=0,
                estimated_history_tokens=0,
                truncated=False,
                source="none",
                reason="no_current_message_reference",
            )
            return empty, usage

        summary_ctx = None
        summary_refreshed = False
        summary_record = None
        try:
            summary_ctx, summary_refreshed = await load_summary_for_conversation(
                session, principal, conversation_id, before_seq
            )
            if summary_ctx is not None:
                summary_record = await get_summary(
                    session, principal, conversation_id
                )
        except Exception:
            summary_ctx = None
            summary_refreshed = False
            summary_record = None

        if summary_refreshed:
            await session.commit()

        summary_boundary = summary_ctx.summarized_through_sequence_no if summary_ctx else -1

        raw_limit = max_messages
        if summary_ctx is not None:
            raw_limit = max(max_messages, CONVERSATION_SUMMARY_KEEP_RECENT_MESSAGES)

        try:
            recent = await load_conversation_messages(
                session, principal, conversation_id,
                before_sequence_no=before_seq,
                limit=raw_limit,
            )
        except HTTPException:
            raise
        except Exception:
            empty = ConversationContext(
                conversation_id=conversation_id,
                recent_messages=[],
                messages_considered=0,
                messages_included=0,
                truncated=False,
                estimated_tokens=0,
            )
            usage = ConversationContextUsage(
                conversation_id=conversation_id,
                history_used=False,
                messages_considered=0,
                messages_included=0,
                estimated_history_tokens=0,
                truncated=False,
                source="none",
                reason="history_unavailable",
            )
            return empty, usage

    selected: List[ContextMessage] = []
    token_total = 0
    truncated = False

    summary_token_budget = CONVERSATION_SUMMARY_MAX_TOKENS if summary_ctx else 0
    raw_token_budget = token_budget

    if summary_ctx is not None:
        raw_token_budget = max(0, token_budget - summary_token_budget)

    recent_filtered = recent
    if summary_boundary >= 0:
        recent_filtered = [m for m in recent if m.sequence_no > summary_boundary]

    for msg in reversed(recent_filtered):
        msg_tokens = estimate_tokens(msg.content)
        if token_total + msg_tokens > raw_token_budget and selected:
            truncated = True
            break
        selected.append(msg)
        token_total += msg_tokens

    selected.reverse()

    total_estimated = token_total + (summary_token_budget if summary_ctx else 0)

    context = ConversationContext(
        conversation_id=conversation_id,
        summary=summary_ctx,
        recent_messages=selected,
        messages_considered=len(recent),
        messages_included=len(selected),
        truncated=truncated,
        estimated_tokens=total_estimated,
    )

    recent_tokens = token_total
    summary_tokens = summary_ctx.estimated_tokens if summary_ctx else 0

    usage = ConversationContextUsage(
        conversation_id=conversation_id,
        history_used=len(selected) > 0 or (summary_ctx is not None),
        messages_considered=len(recent),
        messages_included=len(selected),
        estimated_history_tokens=total_estimated,
        truncated=truncated,
        source="postgresql_summary_and_history" if summary_ctx else "postgresql_history",
        summary_available=summary_ctx is not None,
        summary_used=summary_ctx is not None,
        summary_refreshed=summary_refreshed,
        summary_version=summary_record.version if summary_record else None,
        summarized_through_sequence_no=summary_boundary if summary_boundary >= 0 else None,
        summary_estimated_tokens=summary_tokens if summary_ctx else None,
        recent_messages_included=len(selected),
        estimated_recent_tokens=recent_tokens,
        compression_active=summary_ctx is not None,
    )
    return context, usage
