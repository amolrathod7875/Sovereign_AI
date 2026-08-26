import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Float, Boolean
from datetime import datetime
from typing import Optional, List

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.POSTGRES_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    mime_type = Column(String)
    size = Column(Integer)
    checksum = Column(String)
    doc_type = Column(String, default="pdf")
    status = Column(String, default="uploaded")
    pages = Column(Integer, nullable=True)
    chunks = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id = Column(String, primary_key=True)
    task_type = Column(String)
    status = Column(String, default="PENDING")
    selected_model = Column(String, nullable=True)
    steps = Column(JSON, default=list)
    artifacts = Column(JSON, default=list)
    errors = Column(JSON, default=list)
    external_calls = Column(Integer, default=0)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String, primary_key=True)
    execution_id = Column(String)
    filename = Column(String)
    mime_type = Column(String)
    path = Column(String)
    checksum = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    title = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String)
    role = Column(String)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class NetworkEvent(Base):
    __tablename__ = "network_events"

    id = Column(String, primary_key=True)
    destination_host = Column(String)
    destination_port = Column(Integer)
    action = Column(String)
    execution_id = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


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
