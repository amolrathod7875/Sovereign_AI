import re
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.identity.principal import Principal, get_current_principal, get_current_principal_dep
from app.storage.postgres import (
    async_session,
    Organization,
    User,
    OrganizationMembership,
    Conversation,
    Message,
    MessageAttachment,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/conversations", tags=["conversations"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ConversationSummary(BaseModel):
    id: str
    title: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    last_message_at: Optional[str]
    message_count: int
    archived: bool


class ConversationDetail(ConversationSummary):
    owner_user_id: str
    organization_id: str


class ConversationAttachment(BaseModel):
    id: str
    message_id: str
    conversation_id: str
    document_id: Optional[str]
    filename: str
    mime_type: Optional[str]
    size: Optional[int]
    checksum: Optional[str]
    created_at: Optional[str]


class ConversationMessage(BaseModel):
    id: str
    conversation_id: str
    organization_id: str
    author_user_id: Optional[str]
    sequence_no: int
    role: str
    content: Optional[str]
    created_at: Optional[str]
    status: Optional[str]
    mode: Optional[str]
    task_type: Optional[str]
    routing_model: Optional[str]
    actual_model: Optional[str]
    rag_used: Optional[bool]
    tools_used: Optional[str]
    local_execution: Optional[bool]
    external_calls: Optional[int]
    response_time_seconds: Optional[float]
    model_inference_seconds: Optional[float]
    tokens_per_second: Optional[float]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]
    error_detail: Optional[str]
    display_payload: Optional[dict]
    client_message_id: Optional[str]
    attachments: List[ConversationAttachment] = Field(default_factory=list)


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    archived: Optional[bool] = None


class CreateMessageRequest(BaseModel):
    client_message_id: Optional[str] = None
    role: str = "user"
    content: Optional[str] = None
    mode: Optional[str] = None
    status: Optional[str] = None
    task_type: Optional[str] = None
    routing_model: Optional[str] = None
    actual_model: Optional[str] = None
    rag_used: Optional[bool] = None
    tools_used: Optional[str] = None
    local_execution: Optional[bool] = None
    external_calls: Optional[int] = None
    response_time_seconds: Optional[float] = None
    model_inference_seconds: Optional[float] = None
    tokens_per_second: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    error_detail: Optional[str] = None
    display_payload: Optional[dict] = None
    attachments: Optional[List[dict]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_title_from_content(content: str, max_length: int = 60) -> str:
    if not content:
        return "New conversation"
    text = re.sub(r"\s+", " ", content).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _now() -> datetime:
    return datetime.utcnow()


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


async def _get_principal(request: Request) -> Principal:
    return await get_current_principal_dep(request)


async def _check_db() -> None:
    if async_session is None:
        raise HTTPException(status_code=503, detail="Chat history is unavailable because PostgreSQL is not reachable.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=ConversationDetail)
async def create_conversation(
    req: CreateConversationRequest,
    principal: Principal = Depends(_get_principal),
):
    await _check_db()
    async with async_session() as session:
        conversation = Conversation(
            organization_id=principal.organization_id,
            owner_user_id=principal.user_id,
            title=req.title or "New conversation",
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
        return ConversationDetail(
            id=conversation.id,
            title=conversation.title,
            created_at=_iso(conversation.created_at),
            updated_at=_iso(conversation.updated_at),
            last_message_at=_iso(conversation.last_message_at),
            message_count=0,
            archived=conversation.archived,
            owner_user_id=conversation.owner_user_id,
            organization_id=conversation.organization_id,
        )


@router.get("", response_model=List[ConversationSummary])
async def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(_get_principal),
):
    await _check_db()
    async with async_session() as session:
        subq = (
            select(Message.conversation_id, func.count(Message.id).label("message_count"))
            .where(Message.organization_id == principal.organization_id)
            .group_by(Message.conversation_id)
            .subquery()
        )
        stmt = (
            select(Conversation, subq.c.message_count)
            .outerjoin(subq, Conversation.id == subq.c.conversation_id)
            .where(
                Conversation.organization_id == principal.organization_id,
                Conversation.owner_user_id == principal.user_id,
                Conversation.archived == False,
            )
            .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        rows = result.fetchall()
        out: List[ConversationSummary] = []
        for row in rows:
            conv = row[0]
            count = row[1] or 0
            out.append(
                ConversationSummary(
                    id=conv.id,
                    title=conv.title,
                    created_at=_iso(conv.created_at),
                    updated_at=_iso(conv.updated_at),
                    last_message_at=_iso(conv.last_message_at),
                    message_count=count,
                    archived=conv.archived,
                )
            )
        return out


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    principal: Principal = Depends(_get_principal),
):
    await _check_db()
    async with async_session() as session:
        conv = await session.get(Conversation, conversation_id)
        if not conv or conv.organization_id != principal.organization_id or conv.owner_user_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        count_result = await session.execute(
            select(func.count(Message.id)).where(
                Message.conversation_id == conversation_id,
                Message.organization_id == principal.organization_id,
            )
        )
        message_count = count_result.scalar_one() or 0
        return ConversationDetail(
            id=conv.id,
            title=conv.title,
            created_at=_iso(conv.created_at),
            updated_at=_iso(conv.updated_at),
            last_message_at=_iso(conv.last_message_at),
            message_count=message_count,
            archived=conv.archived,
            owner_user_id=conv.owner_user_id,
            organization_id=conv.organization_id,
        )


@router.patch("/{conversation_id}", response_model=ConversationDetail)
async def update_conversation(
    conversation_id: str,
    req: UpdateConversationRequest,
    principal: Principal = Depends(_get_principal),
):
    await _check_db()
    async with async_session() as session:
        conv = await session.get(Conversation, conversation_id)
        if not conv or conv.organization_id != principal.organization_id or conv.owner_user_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if req.title is not None:
            conv.title = req.title
        if req.archived is not None:
            conv.archived = req.archived
        conv.updated_at = _now()
        await session.commit()
        await session.refresh(conv)
        count_result = await session.execute(
            select(func.count(Message.id)).where(
                Message.conversation_id == conversation_id,
                Message.organization_id == principal.organization_id,
            )
        )
        message_count = count_result.scalar_one() or 0
        return ConversationDetail(
            id=conv.id,
            title=conv.title,
            created_at=_iso(conv.created_at),
            updated_at=_iso(conv.updated_at),
            last_message_at=_iso(conv.last_message_at),
            message_count=message_count,
            archived=conv.archived,
            owner_user_id=conv.owner_user_id,
            organization_id=conv.organization_id,
        )


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    principal: Principal = Depends(_get_principal),
):
    await _check_db()
    async with async_session() as session:
        conv = await session.get(Conversation, conversation_id)
        if not conv or conv.organization_id != principal.organization_id or conv.owner_user_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        await session.delete(conv)
        await session.commit()
    return {"ok": True}


@router.get("/{conversation_id}/messages", response_model=List[ConversationMessage])
async def get_messages(
    conversation_id: str,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(_get_principal),
):
    await _check_db()
    async with async_session() as session:
        conv = await session.get(Conversation, conversation_id)
        if not conv or conv.organization_id != principal.organization_id or conv.owner_user_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.organization_id == principal.organization_id,
            )
            .order_by(Message.sequence_no.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        out: List[ConversationMessage] = []
        for msg in rows:
            attachments_result = await session.execute(
                select(MessageAttachment).where(MessageAttachment.message_id == msg.id)
            )
            attachments = [
                ConversationAttachment(
                    id=a.id,
                    message_id=a.message_id,
                    conversation_id=a.conversation_id,
                    document_id=a.document_id,
                    filename=a.filename,
                    mime_type=a.mime_type,
                    size=a.size,
                    checksum=a.checksum,
                    created_at=_iso(a.created_at),
                )
                for a in attachments_result.scalars().all()
            ]
            out.append(
                ConversationMessage(
                    id=msg.id,
                    conversation_id=msg.conversation_id,
                    organization_id=msg.organization_id,
                    author_user_id=msg.author_user_id,
                    sequence_no=msg.sequence_no,
                    role=msg.role,
                    content=msg.content,
                    created_at=_iso(msg.created_at),
                    status=msg.status,
                    mode=msg.mode,
                    task_type=msg.task_type,
                    routing_model=msg.routing_model,
                    actual_model=msg.actual_model,
                    rag_used=msg.rag_used,
                    tools_used=msg.tools_used,
                    local_execution=msg.local_execution,
                    external_calls=msg.external_calls,
                    response_time_seconds=msg.response_time_seconds,
                    model_inference_seconds=msg.model_inference_seconds,
                    tokens_per_second=msg.tokens_per_second,
                    prompt_tokens=msg.prompt_tokens,
                    completion_tokens=msg.completion_tokens,
                    total_tokens=msg.total_tokens,
                    error_detail=msg.error_detail,
                    display_payload=msg.display_payload,
                    client_message_id=msg.client_message_id,
                    attachments=attachments,
                )
            )
        return out


@router.post("/{conversation_id}/messages", response_model=ConversationMessage)
async def create_message(
    conversation_id: str,
    req: CreateMessageRequest,
    principal: Principal = Depends(_get_principal),
):
    await _check_db()
    async with async_session() as session:
        conv = await session.get(Conversation, conversation_id)
        if not conv or conv.organization_id != principal.organization_id or conv.owner_user_id != principal.user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Idempotency: return existing client_message_id if already present
        if req.client_message_id:
            existing = await session.execute(
                select(Message).where(
                    Message.conversation_id == conversation_id,
                    Message.client_message_id == req.client_message_id,
                )
            )
            found = existing.scalar_one_or_none()
            if found:
                attachments_result = await session.execute(
                    select(MessageAttachment).where(MessageAttachment.message_id == found.id)
                )
                attachments = [
                    ConversationAttachment(
                        id=a.id,
                        message_id=a.message_id,
                        conversation_id=a.conversation_id,
                        document_id=a.document_id,
                        filename=a.filename,
                        mime_type=a.mime_type,
                        size=a.size,
                        checksum=a.checksum,
                        created_at=_iso(a.created_at),
                    )
                    for a in attachments_result.scalars().all()
                ]
                return ConversationMessage(
                    id=found.id,
                    conversation_id=found.conversation_id,
                    organization_id=found.organization_id,
                    author_user_id=found.author_user_id,
                    sequence_no=found.sequence_no,
                    role=found.role,
                    content=found.content,
                    created_at=_iso(found.created_at),
                    status=found.status,
                    mode=found.mode,
                    task_type=found.task_type,
                    routing_model=found.routing_model,
                    actual_model=found.actual_model,
                    rag_used=found.rag_used,
                    tools_used=found.tools_used,
                    local_execution=found.local_execution,
                    external_calls=found.external_calls,
                    response_time_seconds=found.response_time_seconds,
                    model_inference_seconds=found.model_inference_seconds,
                    tokens_per_second=found.tokens_per_second,
                    prompt_tokens=found.prompt_tokens,
                    completion_tokens=found.completion_tokens,
                    total_tokens=found.total_tokens,
                    error_detail=found.error_detail,
                    display_payload=found.display_payload,
                    client_message_id=found.client_message_id,
                    attachments=attachments,
                )

        # Auto-title on first user message
        title_updated = False
        if conv.title in (None, "", "New conversation") and req.role == "user" and req.content:
            conv.title = _derive_title_from_content(req.content)
            title_updated = True

        # Sequence no
        next_seq = conv.next_sequence_no
        conv.next_sequence_no = next_seq + 1

        # Author
        author_user_id = principal.user_id if req.role == "user" else None

        msg = Message(
            conversation_id=conversation_id,
            organization_id=principal.organization_id,
            author_user_id=author_user_id,
            sequence_no=next_seq,
            role=req.role,
            content=req.content,
            status=req.status,
            mode=req.mode,
            task_type=req.task_type,
            routing_model=req.routing_model,
            actual_model=req.actual_model,
            rag_used=req.rag_used,
            tools_used=req.tools_used,
            local_execution=req.local_execution,
            external_calls=req.external_calls,
            response_time_seconds=req.response_time_seconds,
            model_inference_seconds=req.model_inference_seconds,
            tokens_per_second=req.tokens_per_second,
            prompt_tokens=req.prompt_tokens,
            completion_tokens=req.completion_tokens,
            total_tokens=req.total_tokens,
            error_detail=req.error_detail,
            display_payload=req.display_payload,
            client_message_id=req.client_message_id,
        )
        session.add(msg)

        # Update conversation metadata
        conv.last_message_at = _now()
        conv.updated_at = _now()

        await session.commit()
        await session.refresh(msg)

        # Attachments
        attachments_out: List[ConversationAttachment] = []
        if req.attachments:
            for att in req.attachments:
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
                attachments_out.append(
                    ConversationAttachment(
                        id=ma.id,
                        message_id=ma.message_id,
                        conversation_id=ma.conversation_id,
                        document_id=ma.document_id,
                        filename=ma.filename,
                        mime_type=ma.mime_type,
                        size=ma.size,
                        checksum=ma.checksum,
                        created_at=_iso(ma.created_at),
                    )
                )
            await session.commit()

        return ConversationMessage(
            id=msg.id,
            conversation_id=msg.conversation_id,
            organization_id=msg.organization_id,
            author_user_id=msg.author_user_id,
            sequence_no=msg.sequence_no,
            role=msg.role,
            content=msg.content,
            created_at=_iso(msg.created_at),
            status=msg.status,
            mode=msg.mode,
            task_type=msg.task_type,
            routing_model=msg.routing_model,
            actual_model=msg.actual_model,
            rag_used=msg.rag_used,
            tools_used=msg.tools_used,
            local_execution=msg.local_execution,
            external_calls=msg.external_calls,
            response_time_seconds=msg.response_time_seconds,
            model_inference_seconds=msg.model_inference_seconds,
            tokens_per_second=msg.tokens_per_second,
            prompt_tokens=msg.prompt_tokens,
            completion_tokens=msg.completion_tokens,
            total_tokens=msg.total_tokens,
            error_detail=msg.error_detail,
            display_payload=msg.display_payload,
            client_message_id=msg.client_message_id,
            attachments=attachments_out,
        )
