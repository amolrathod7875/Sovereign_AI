from typing import List, Optional
from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.schemas import ConversationSummaryContext
from app.identity.principal import Principal
from app.storage.postgres import (
    ConversationSummaryRecord,
    Message,
    Conversation,
)
from app.context.budget import (
    CONVERSATION_SUMMARY_TRIGGER_MESSAGES,
    CONVERSATION_SUMMARY_KEEP_RECENT_MESSAGES,
    CONVERSATION_SUMMARY_REFRESH_MIN_MESSAGES,
    estimate_tokens,
)


class SummaryError(Exception):
    pass


async def get_summary(
    session: AsyncSession,
    principal: Principal,
    conversation_id: str,
) -> Optional[ConversationSummaryRecord]:
    stmt = (
        select(ConversationSummaryRecord)
        .where(ConversationSummaryRecord.conversation_id == conversation_id)
        .where(ConversationSummaryRecord.organization_id == principal.organization_id)
        .where(ConversationSummaryRecord.owner_user_id == principal.user_id)
        .execution_options(populate_existing=True)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_summary(
    session: AsyncSession,
    principal: Principal,
    conversation_id: str,
    summary_text: str,
    summarized_through_sequence_no: int,
    source_message_count: int,
    estimated_tokens: int,
    model_id: Optional[str],
    new_version: int,
) -> ConversationSummaryRecord:
    existing = await get_summary(session, principal, conversation_id)
    if existing is not None:
        if existing.summarized_through_sequence_no >= summarized_through_sequence_no:
            raise SummaryError(
                f"boundary_regression: existing={existing.summarized_through_sequence_no} new={summarized_through_sequence_no}"
            )
        existing.summary_text = summary_text
        existing.summarized_through_sequence_no = summarized_through_sequence_no
        existing.source_message_count = source_message_count
        existing.estimated_tokens = estimated_tokens
        existing.model_id = model_id
        existing.version = new_version
        session.add(existing)
        return existing

    record = ConversationSummaryRecord(
        conversation_id=conversation_id,
        organization_id=principal.organization_id,
        owner_user_id=principal.user_id,
        summary_text=summary_text,
        summarized_through_sequence_no=summarized_through_sequence_no,
        source_message_count=source_message_count,
        estimated_tokens=estimated_tokens,
        model_id=model_id,
        version=new_version,
    )
    session.add(record)
    return record


async def get_messages_for_summary(
    session: AsyncSession,
    principal: Principal,
    conversation_id: str,
    after_sequence_no: int,
    before_sequence_no: int,
) -> List[Message]:
    stmt = (
        select(Message.id, Message.sequence_no, Message.role, Message.content, Message.status)
        .where(Message.conversation_id == conversation_id)
        .where(Message.role.in_(["user", "assistant"]))
        .where(Message.content.is_not(None))
        .where(Message.content != "")
        .where(
            or_(
                Message.role != "assistant",
                Message.status != "FAILED",
                Message.status.is_(None),
            )
        )
        .where(Message.sequence_no > after_sequence_no)
        .where(Message.sequence_no < before_sequence_no)
        .order_by(Message.sequence_no.asc())
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        type(
            "Msg",
            (object,),
            {
                "id": row.id,
                "sequence_no": row.sequence_no,
                "role": row.role,
                "content": row.content,
                "status": row.status,
            },
        )()
        for row in rows
    ]


async def get_latest_sequence_no(
    session: AsyncSession,
    conversation_id: str,
) -> Optional[int]:
    stmt = select(func.max(Message.sequence_no)).where(Message.conversation_id == conversation_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row


async def count_eligible_messages_before(
    session: AsyncSession,
    conversation_id: str,
    before_sequence_no: int,
    after_sequence_no: int = -1,
) -> int:
    stmt = (
        select(func.count(Message.id))
        .where(Message.conversation_id == conversation_id)
        .where(Message.role.in_(["user", "assistant"]))
        .where(Message.content.is_not(None))
        .where(Message.content != "")
        .where(
            or_(
                Message.role != "assistant",
                Message.status != "FAILED",
                Message.status.is_(None),
            )
        )
        .where(Message.sequence_no > after_sequence_no)
        .where(Message.sequence_no < before_sequence_no)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row or 0


def compute_summary_cutoff(
    total_prior_messages: int,
    keep_recent: Optional[int] = None,
    trigger_messages: Optional[int] = None,
) -> Optional[int]:
    """Compute the sequence number up to which a summary should cover.

    Returns None if no summary should be generated.
    """
    if keep_recent is None:
        keep_recent = CONVERSATION_SUMMARY_KEEP_RECENT_MESSAGES
    if trigger_messages is None:
        trigger_messages = CONVERSATION_SUMMARY_TRIGGER_MESSAGES
    if total_prior_messages < trigger_messages:
        return None
    cutoff = total_prior_messages - keep_recent
    if cutoff <= 0:
        return None
    return cutoff


def build_summary_context(
    existing_summary: Optional[ConversationSummaryContext],
    new_messages: list,
) -> str:
    parts: List[str] = []
    if existing_summary is not None and existing_summary.text:
        parts.append(f"EXISTING SUMMARY:\n{existing_summary.text}\n")
    if new_messages:
        parts.append("NEW VISIBLE MESSAGES:\n")
        for msg in new_messages:
            parts.append(f"[sequence {msg.sequence_no}][{msg.role}]\n{msg.content}\n")
    return "\n".join(parts)
