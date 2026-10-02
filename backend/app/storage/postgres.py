import logging
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Text,
    JSON,
    Float,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import (
    declarative_base,
    Mapped,
    mapped_column,
    relationship,
)
from sqlalchemy.sql import text

from app.config import settings

logger = logging.getLogger(__name__)

# The app is fully async, so the engine requires an async driver
# (postgresql+asyncpg://). Creating the engine eagerly is safe, but we guard
# against configuration problems so the rest of the backend still imports cleanly.
try:
    engine = create_async_engine(settings.POSTGRES_URL, echo=False)
except Exception as e:  # pragma: no cover - defensive
    logger.error("Failed to create Postgres engine: %s", e)
    engine = None

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False) if engine else None

Base = declarative_base()


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    external_subject: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"

    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_user"),
    )


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    next_sequence_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_conversations_org_owner", "organization_id", "owner_user_id"),
        Index("ix_conversations_last_message_at", "last_message_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    author_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    task_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    routing_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    actual_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rag_used: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    tools_used: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    local_execution: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    external_calls: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_inference_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tokens_per_second: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    display_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    client_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence_no", name="uq_message_conversation_sequence"),
        UniqueConstraint("conversation_id", "client_message_id", name="uq_message_client_id"),
        Index("ix_messages_created_at", "created_at"),
    )


class ConversationSummaryRecord(Base):
    __tablename__ = "conversation_summaries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    summarized_through_sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    source_message_count: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_conversation_summaries_org_owner", "organization_id", "owner_user_id"),
        Index("ix_conversation_summaries_updated_at", "updated_at"),
    )


class MessageAttachment(Base):
    __tablename__ = "message_attachments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Existing tables (preserved)
# ---------------------------------------------------------------------------

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    doc_type: Mapped[str] = mapped_column(String, default="pdf", nullable=False)
    status: Mapped[str] = mapped_column(String, default="uploaded", nullable=False)
    pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chunks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="PENDING", nullable=False)
    selected_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    steps: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    artifacts: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    errors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    external_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    execution_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    filename: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class NetworkEvent(Base):
    __tablename__ = "network_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    destination_host: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    destination_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    execution_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def init_db():
    """Create tables if Postgres is reachable.

    Degrades gracefully when no database is configured/available (e.g. local
    standalone run): the sovereign agent and embedded RAG do not require Postgres,
    so the backend still boots and serves the offline path.
    """
    if engine is None:
        logger.warning("Postgres engine not configured - skipping DB init (offline mode).")
        return
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.error("Postgres init failed (continuing offline): %s", e)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def ensure_dev_principal() -> None:
    """Ensure the local development principal exists.

    M1 only. Future Phase A will replace this with real authentication.
    """
    if not engine:
        return
    async with async_session() as session:
        try:
            org = await session.get(Organization, settings.SOVEREIGN_DEV_ORGANIZATION_ID)
            if not org:
                org = Organization(
                    id=settings.SOVEREIGN_DEV_ORGANIZATION_ID,
                    name="Local Development Organization",
                )
                session.add(org)

            user = await session.get(User, settings.SOVEREIGN_DEV_USER_ID)
            if not user:
                user = User(
                    id=settings.SOVEREIGN_DEV_USER_ID,
                    display_name=settings.SOVEREIGN_DEV_DISPLAY_NAME,
                )
                session.add(user)

            membership = await session.get(
                OrganizationMembership,
                (settings.SOVEREIGN_DEV_ORGANIZATION_ID, settings.SOVEREIGN_DEV_USER_ID),
            )
            if not membership:
                membership = OrganizationMembership(
                    organization_id=settings.SOVEREIGN_DEV_ORGANIZATION_ID,
                    user_id=settings.SOVEREIGN_DEV_USER_ID,
                    role="owner",
                    status="active",
                )
                session.add(membership)

            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Backward-compatible helper functions (preserved from original module)
# ---------------------------------------------------------------------------

async def get_all_documents() -> List[Document]:
    async with async_session() as session:
        result = await session.execute("SELECT * FROM documents ORDER BY created_at DESC")
        rows = result.fetchall()
        return [Document(**row._asdict()) for row in rows]


async def get_document_by_id(document_id: str) -> Optional[Document]:
    async with async_session() as session:
        result = await session.execute(
            f"SELECT * FROM documents WHERE id = '{document_id}'"
        )
        row = result.fetchone()
        if row:
            return Document(**row._asdict())
        return None


async def delete_document(document_id: str):
    async with async_session() as session:
        await session.execute(f"DELETE FROM documents WHERE id = '{document_id}'")
        await session.commit()


async def create_execution(execution_id: str, task_type: str) -> AgentExecution:
    execution = AgentExecution(
        id=execution_id,
        task_type=task_type,
        status="RUNNING",
        started_at=datetime.utcnow(),
    )
    async with async_session() as session:
        session.add(execution)
        await session.commit()
    return execution


async def update_execution(
    execution_id: str,
    status: str = None,
    selected_model: str = None,
    steps: list = None,
    artifacts: list = None,
    errors: list = None,
    external_calls: int = None,
):
    async with async_session() as session:
        updates = []
        if status:
            updates.append(f"status = '{status}'")
        if selected_model:
            updates.append(f"selected_model = '{selected_model}'")
        if steps:
            import json
            updates.append(f"steps = '{json.dumps(steps)}'")
        if artifacts:
            import json
            updates.append(f"artifacts = '{json.dumps(artifacts)}'")
        if errors:
            import json
            updates.append(f"errors = '{json.dumps(errors)}'")
        if external_calls is not None:
            updates.append(f"external_calls = {external_calls}")
        if status == "COMPLETED" or status == "FAILED":
            updates.append(f"completed_at = '{datetime.utcnow()}'")

        if updates:
            query = f"UPDATE agent_executions SET {', '.join(updates)} WHERE id = '{execution_id}'"
            await session.execute(query)
            await session.commit()


async def get_execution_by_id(execution_id: str) -> Optional[AgentExecution]:
    async with async_session() as session:
        result = await session.execute(
            f"SELECT * FROM agent_executions WHERE id = '{execution_id}'"
        )
        row = result.fetchone()
        if row:
            return AgentExecution(**row._asdict())
        return None


async def list_executions(limit: int = 50, offset: int = 0, task_type: str = None) -> List[AgentExecution]:
    async with async_session() as session:
        query = "SELECT * FROM agent_executions"
        if task_type:
            query += f" WHERE task_type = '{task_type}'"
        query += f" ORDER BY started_at DESC LIMIT {limit} OFFSET {offset}"
        result = await session.execute(query)
        rows = result.fetchall()
        return [AgentExecution(**row._asdict()) for row in rows]


async def create_artifact(artifact_id: str, execution_id: str, filename: str, mime_type: str, path: str, checksum: str) -> Artifact:
    artifact = Artifact(
        id=artifact_id,
        execution_id=execution_id,
        filename=filename,
        mime_type=mime_type,
        path=path,
        checksum=checksum,
    )
    async with async_session() as session:
        session.add(artifact)
        await session.commit()
    return artifact


async def log_network_event(event_id: str, destination_host: str, destination_port: int, action: str, execution_id: str = None):
    event = NetworkEvent(
        id=event_id,
        destination_host=destination_host,
        destination_port=destination_port,
        action=action,
        execution_id=execution_id,
    )
    async with async_session() as session:
        session.add(event)
        await session.commit()
