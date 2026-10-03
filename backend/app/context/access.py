"""Central conversation-access authorization helper for M6.

One authoritative predicate for conversation ownership so context builders,
memory search, and APIs do not implement competing authorization logic.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.storage.postgres import Conversation
from app.identity.principal import Principal


async def validate_conversation_access(
    session: AsyncSession,
    principal: Principal,
    conversation_id: str,
) -> Optional[Conversation]:
    """Return the conversation iff principal owns it.

    Returns None when the conversation is missing or belongs to another user/org.
    """
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .where(Conversation.organization_id == principal.organization_id)
        .where(Conversation.owner_user_id == principal.user_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
