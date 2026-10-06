import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.storage.postgres import (
    Conversation,
    Message,
    MessageAttachment,
)


def _derive_title_from_content(content: str, max_length: int = 60) -> str:
    if not content:
        return "New conversation"
    text = " ".join(content.split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


async def _get_conversation(
    session: AsyncSession,
    conversation_id: str,
    organization_id: str,
    user_id: str,
) -> Conversation:
    conv = await session.get(Conversation, conversation_id)
    if not conv or conv.organization_id != organization_id or conv.owner_user_id != user_id:
        raise ValueError("Conversation not found")
    return conv


async def persist_user_message(
    session: AsyncSession,
    *,
    conversation_id: str,
    organization_id: str,
    principal,
    content: Optional[str] = None,
    client_message_id: Optional[str] = None,
    mode: Optional[str] = None,
    attachments: Optional[List[dict]] = None,
) -> Message:
    """Persist a trusted user-authored message.

    Caller MUST be an authenticated principal. The browser cannot call this
    function directly.
    """
    conv = await _get_conversation(session, conversation_id, organization_id, principal.user_id)

    if client_message_id:
        existing = await session.execute(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.client_message_id == client_message_id,
            )
        )
        found = existing.scalar_one_or_none()
        if found:
            return found

    if conv.title in (None, "", "New conversation") and content:
        conv.title = _derive_title_from_content(content)

    next_seq = conv.next_sequence_no
    conv.next_sequence_no = next_seq + 1

    msg = Message(
        conversation_id=conversation_id,
        organization_id=organization_id,
        author_user_id=principal.user_id,
        sequence_no=next_seq,
        role="user",
        content=content,
        mode=mode,
        client_message_id=client_message_id,
    )
    session.add(msg)
    conv.last_message_at = datetime.utcnow()
    conv.updated_at = datetime.utcnow()

    await session.commit()
    await session.refresh(msg)

    if attachments:
        for att in attachments:
            ma = MessageAttachment(
                message_id=msg.id,
                conversation_id=conversation_id,
                document_id=att.get("document_id"),
                filename=att["filename"],
                mime_type=att.get("mime_type"),
                size=att.get("size"),
                checksum=att.get("checksum"),
            )
            session.add(ma)
        await session.commit()

    return msg


async def persist_assistant_message(
    session: AsyncSession,
    *,
    conversation_id: str,
    organization_id: str,
    principal,
    content: Optional[str] = None,
    status: Optional[str] = None,
    mode: Optional[str] = None,
    task_type: Optional[str] = None,
    routing_model: Optional[str] = None,
    actual_model: Optional[str] = None,
    rag_used: Optional[bool] = None,
    tools_used: Optional[str] = None,
    local_execution: Optional[bool] = None,
    external_calls: Optional[int] = None,
    response_time_seconds: Optional[float] = None,
    model_inference_seconds: Optional[float] = None,
    tokens_per_second: Optional[float] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    error_detail: Optional[str] = None,
    display_payload: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
) -> Message:
    """Persist a trusted backend-generated assistant message.

    This function MUST NOT be exposed as a public browser endpoint.
    The caller is responsible for scoping to the authenticated principal.
    role and author_user_id are forced server-side.
    """
    conv = await _get_conversation(session, conversation_id, organization_id, principal.user_id)

    if idempotency_key:
        existing = await session.execute(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.client_message_id == idempotency_key,
            )
        )
        found = existing.scalar_one_or_none()
        if found:
            return found

    next_seq = conv.next_sequence_no
    conv.next_sequence_no = next_seq + 1

    msg = Message(
        conversation_id=conversation_id,
        organization_id=organization_id,
        author_user_id=None,
        sequence_no=next_seq,
        role="assistant",
        content=content,
        status=status,
        mode=mode,
        task_type=task_type,
        routing_model=routing_model,
        actual_model=actual_model,
        rag_used=rag_used,
        tools_used=tools_used,
        local_execution=local_execution,
        external_calls=external_calls,
        response_time_seconds=response_time_seconds,
        model_inference_seconds=model_inference_seconds,
        tokens_per_second=tokens_per_second,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        error_detail=error_detail,
        display_payload=display_payload,
        client_message_id=idempotency_key,
    )
    session.add(msg)
    conv.last_message_at = datetime.utcnow()
    conv.updated_at = datetime.utcnow()

    await session.commit()
    await session.refresh(msg)
    return msg
