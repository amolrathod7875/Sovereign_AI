from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.schemas import ContextMessage
from app.identity.principal import Principal
from app.storage.postgres import Message, Conversation


async def load_conversation_messages(
    session: AsyncSession,
    principal: Principal,
    conversation_id: str,
    before_sequence_no: Optional[int] = None,
    limit: int = 20,
) -> List[ContextMessage]:
    conv = await session.get(Conversation, conversation_id)
    if not conv or conv.organization_id != principal.organization_id or conv.owner_user_id != principal.user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    stmt = (
        select(Message.id, Message.sequence_no, Message.role, Message.content)
        .where(Message.conversation_id == conversation_id)
        .where(Message.role.in_(["user", "assistant"]))
        .where(Message.content.is_not(None))
        .where(Message.content != "")
    )
    if before_sequence_no is not None:
        stmt = stmt.where(Message.sequence_no < before_sequence_no)
    stmt = stmt.order_by(desc(Message.sequence_no)).limit(limit)

    result = await session.execute(stmt)
    rows = result.all()
    rows.reverse()

    return [
        ContextMessage(
            role=row.role,
            content=row.content,
            message_id=row.id,
            sequence_no=row.sequence_no,
        )
        for row in rows
    ]
