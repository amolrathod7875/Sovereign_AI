from typing import List, Optional, Tuple
from fastapi import HTTPException

from app.context.budget import CONVERSATION_CONTEXT_MAX_MESSAGES, CONVERSATION_CONTEXT_TOKEN_BUDGET, estimate_tokens
from app.context.repository import load_conversation_messages
from app.context.schemas import ContextMessage, ConversationContext, ConversationContextUsage
from app.identity.principal import Principal
from app.storage.postgres import Message, async_session


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

        try:
            recent = await load_conversation_messages(
                session, principal, conversation_id,
                before_sequence_no=before_seq,
                limit=max_messages,
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

    for msg in reversed(recent):
        msg_tokens = estimate_tokens(msg.content)
        if token_total + msg_tokens > token_budget and selected:
            truncated = True
            break
        selected.append(msg)
        token_total += msg_tokens

    selected.reverse()

    context = ConversationContext(
        conversation_id=conversation_id,
        recent_messages=selected,
        messages_considered=len(recent),
        messages_included=len(selected),
        truncated=truncated,
        estimated_tokens=token_total,
    )
    usage = ConversationContextUsage(
        conversation_id=conversation_id,
        history_used=len(selected) > 0,
        messages_considered=len(recent),
        messages_included=len(selected),
        estimated_history_tokens=token_total,
        truncated=truncated,
        source="postgresql_history",
    )
    return context, usage
