"""Phase M5.1 — Memory authorization hardening tests."""
from __future__ import annotations

import asyncio
import logging
import math
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, text, or_, delete as sql_delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.identity.principal import Principal
from app.memory.schemas import MemoryOutboxOperation, MemoryOutboxStatus, MemoryScope, MemoryType
from app.memory.repository import MemoryRepository
from app.memory.vector_store import MemoryVectorStore, _stable_point_id
from app.memory.indexer import OutboxProcessor
from app.memory.search import MemorySemanticSearch, MemorySearchResponse
from app.storage.postgres import (
    Base,
    Organization,
    User,
    Conversation,
    ConversationMemory,
    MemoryProvenance,
    MemoryIndexOutbox,
    async_session as _app_async_session,
)
import app.storage.postgres as postgres_mod
import app.memory.indexer as idx_mod
import app.memory.search as search_mod
import app.api.memory as memory_mod

TEST_DB_URL = settings.POSTGRES_URL

test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
test_async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True)
async def _patch_async_sessions():
    original_postgres = postgres_mod.async_session
    original_indexer = idx_mod.async_session
    original_search = search_mod.async_session
    original_memory = memory_mod.async_session
    postgres_mod.async_session = test_async_session
    idx_mod.async_session = test_async_session
    search_mod.async_session = test_async_session
    memory_mod.async_session = test_async_session
    try:
        yield
    finally:
        postgres_mod.async_session = original_postgres
        idx_mod.async_session = original_indexer
        search_mod.async_session = original_search
        memory_mod.async_session = original_memory


def _principal(user_id: str, org_id: str, authenticated: bool = True) -> Principal:
    return Principal(user_id=user_id, organization_id=org_id, roles=["member"], authenticated=authenticated, source="test")


def _make_org(session: AsyncSession, org_id: str, name: str = "Test Org") -> Organization:
    org = Organization(id=org_id, name=name)
    session.add(org)
    return org


def _make_user(session: AsyncSession, user_id: str, display_name: str = "Test User") -> User:
    user = User(id=user_id, display_name=display_name)
    session.add(user)
    return user


def _make_conv(session: AsyncSession, org_id: str, user_id: str) -> Conversation:
    conv = Conversation(organization_id=org_id, owner_user_id=user_id, title="Test Conv")
    session.add(conv)
    return conv


async def _commit(session: AsyncSession):
    await session.commit()


async def _cleanup_all_outbox(session: AsyncSession):
    from sqlalchemy import delete
    await session.execute(delete(MemoryIndexOutbox))
    await session.execute(delete(ConversationMemory))
    await session.execute(delete(Conversation))
    await session.commit()


def _make_memory(
    session: AsyncSession,
    principal: Principal,
    scope: str = MemoryScope.PERSONAL.value,
    conversation_id: Optional[str] = None,
    active: bool = True,
    version: int = 1,
    content: str = "User prefers pressure in bar.",
    memory_type: str = MemoryType.USER_PREFERENCE.value,
) -> ConversationMemory:
    memory = ConversationMemory(
        id=str(uuid.uuid4()),
        organization_id=principal.organization_id,
        user_id=principal.user_id if scope in (MemoryScope.PERSONAL.value, MemoryScope.CONVERSATION.value) else None,
        conversation_id=conversation_id if scope == MemoryScope.CONVERSATION.value else None,
        scope=scope,
        memory_type=memory_type,
        content=content,
        normalized_content=content.strip().lower(),
        importance=0.9,
        confidence=0.95,
        active=active,
        version=version,
    )
    session.add(memory)
    return memory


def _make_outbox(
    session: AsyncSession,
    memory_id: str,
    operation: str = MemoryOutboxOperation.UPSERT.value,
    status: str = MemoryOutboxStatus.PENDING.value,
) -> MemoryIndexOutbox:
    outbox = MemoryIndexOutbox(
        id=str(uuid.uuid4()),
        memory_id=memory_id,
        operation=operation,
        status=status,
    )
    session.add(outbox)
    return outbox


# ---------------------------------------------------------------------------
# Deterministic embedder for search tests
# ---------------------------------------------------------------------------

class DeterministicEmbedder:
    def __init__(self, model_path=None, dim: int = 384):
        self.model_path = model_path
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        result = []
        for text in texts:
            vec = []
            for i in range(self._dim):
                val = math.sin(hash(text) % 10000 + i) % 2.0 - 1.0
                norm = val / (self._dim ** 0.5)
                vec.append(norm)
            result.append(vec)
        return result


# ---------------------------------------------------------------------------
# A. Same org, foreign PERSONAL GET -> 404
# B. Same org, foreign PERSONAL DELETE -> 404
# ---------------------------------------------------------------------------

class TestForeignPersonalIsolation:
    @pytest.mark.asyncio
    async def test_foreign_personal_get_404(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_a)
        _make_user(db_session, user_b)
        await _commit(db_session)

        p_a = _principal(user_a, org_id)
        p_b = _principal(user_b, org_id)
        conv = _make_conv(db_session, org_id, user_a)
        await _commit(db_session)

        repo = MemoryRepository(db_session)
        memory = _make_memory(db_session, p_a, scope=MemoryScope.PERSONAL.value)
        await _commit(db_session)

        from app.api.memory import get_memory as api_get
        with pytest.raises(HTTPException) as exc_info:
            await api_get(memory.id, principal=p_b)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_foreign_personal_delete_404(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_a)
        _make_user(db_session, user_b)
        await _commit(db_session)

        p_a = _principal(user_a, org_id)
        p_b = _principal(user_b, org_id)
        conv = _make_conv(db_session, org_id, user_a)
        await _commit(db_session)

        repo = MemoryRepository(db_session)
        memory = _make_memory(db_session, p_a, scope=MemoryScope.PERSONAL.value)
        await _commit(db_session)

        from app.api.memory import delete_memory as api_delete
        with pytest.raises(HTTPException) as exc_info:
            await api_delete(memory.id, principal=p_b)
        assert exc_info.value.status_code == 404

        # Verify no side effects
        reloaded = await repo.get_memory(p_a, memory.id)
        assert reloaded is not None
        await db_session.refresh(reloaded)
        assert reloaded.active is True

        outbox = await repo.list_outbox_for_memory(memory.id)
        delete_events = [o for o in outbox if o.operation == "DELETE"]
        assert len(delete_events) == 0


# ---------------------------------------------------------------------------
# C. Same org, foreign CONVERSATION GET -> 404
# D. Same org, foreign CONVERSATION DELETE -> 404
# ---------------------------------------------------------------------------

class TestForeignConversationIsolation:
    @pytest.mark.asyncio
    async def test_foreign_conversation_get_404(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_a)
        _make_user(db_session, user_b)
        await _commit(db_session)

        p_a = _principal(user_a, org_id)
        p_b = _principal(user_b, org_id)
        conv_a = _make_conv(db_session, org_id, user_a)
        conv_b = _make_conv(db_session, org_id, user_b)
        await _commit(db_session)

        repo = MemoryRepository(db_session)
        memory = _make_memory(db_session, p_a, scope=MemoryScope.CONVERSATION.value, conversation_id=conv_a.id)
        await _commit(db_session)

        from app.api.memory import get_memory as api_get
        with pytest.raises(HTTPException) as exc_info:
            await api_get(memory.id, principal=p_b)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_foreign_conversation_delete_404(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_a)
        _make_user(db_session, user_b)
        await _commit(db_session)

        p_a = _principal(user_a, org_id)
        p_b = _principal(user_b, org_id)
        conv_a = _make_conv(db_session, org_id, user_a)
        conv_b = _make_conv(db_session, org_id, user_b)
        await _commit(db_session)

        repo = MemoryRepository(db_session)
        memory = _make_memory(db_session, p_a, scope=MemoryScope.CONVERSATION.value, conversation_id=conv_a.id)
        await _commit(db_session)

        from app.api.memory import delete_memory as api_delete
        with pytest.raises(HTTPException) as exc_info:
            await api_delete(memory.id, principal=p_b)
        assert exc_info.value.status_code == 404

        # Verify no side effects
        reloaded = await repo.get_memory(p_a, memory.id)
        assert reloaded is not None
        await db_session.refresh(reloaded)
        assert reloaded.active is True

        outbox = await repo.list_outbox_for_memory(memory.id)
        delete_events = [o for o in outbox if o.operation == "DELETE"]
        assert len(delete_events) == 0


# ---------------------------------------------------------------------------
# E. Foreign org GET -> 404
# F. Foreign org DELETE -> 404
# ---------------------------------------------------------------------------

class TestForeignOrgIsolation:
    @pytest.mark.asyncio
    async def test_foreign_org_get_404(self, db_session: AsyncSession):
        org_a = str(uuid.uuid4())
        org_b = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_a)
        _make_org(db_session, org_b)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p_a = _principal(user_id, org_a)
        p_b = _principal(user_id, org_b)
        conv = _make_conv(db_session, org_a, user_id)
        await _commit(db_session)

        repo = MemoryRepository(db_session)
        memory = _make_memory(db_session, p_a, scope=MemoryScope.PERSONAL.value)
        await _commit(db_session)

        from app.api.memory import get_memory as api_get
        with pytest.raises(HTTPException) as exc_info:
            await api_get(memory.id, principal=p_b)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_foreign_org_delete_404(self, db_session: AsyncSession):
        org_a = str(uuid.uuid4())
        org_b = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_a)
        _make_org(db_session, org_b)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p_a = _principal(user_id, org_a)
        p_b = _principal(user_id, org_b)
        conv = _make_conv(db_session, org_a, user_id)
        await _commit(db_session)

        repo = MemoryRepository(db_session)
        memory = _make_memory(db_session, p_a, scope=MemoryScope.PERSONAL.value)
        await _commit(db_session)

        from app.api.memory import delete_memory as api_delete
        with pytest.raises(HTTPException) as exc_info:
            await api_delete(memory.id, principal=p_b)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# G. Own PERSONAL GET -> success
# H. Own CONVERSATION GET -> success
# I. Own CONVERSATION DELETE -> success
# ---------------------------------------------------------------------------

class TestOwnMemoryAccess:
    @pytest.mark.asyncio
    async def test_own_personal_get_success(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = _make_conv(db_session, org_id, user_id)
        await _commit(db_session)

        repo = MemoryRepository(db_session)
        memory = _make_memory(db_session, p, scope=MemoryScope.PERSONAL.value)
        await _commit(db_session)

        from app.api.memory import get_memory as api_get
        result = await api_get(memory.id, principal=p)
        assert result.id == memory.id

    @pytest.mark.asyncio
    async def test_own_conversation_get_success(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = _make_conv(db_session, org_id, user_id)
        await _commit(db_session)

        repo = MemoryRepository(db_session)
        memory = _make_memory(db_session, p, scope=MemoryScope.CONVERSATION.value, conversation_id=conv.id)
        await _commit(db_session)

        from app.api.memory import get_memory as api_get
        result = await api_get(memory.id, principal=p)
        assert result.id == memory.id

    @pytest.mark.asyncio
    async def test_own_conversation_delete_success(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = _make_conv(db_session, org_id, user_id)
        await _commit(db_session)

        repo = MemoryRepository(db_session)
        memory = _make_memory(db_session, p, scope=MemoryScope.CONVERSATION.value, conversation_id=conv.id)
        await _commit(db_session)

        from app.api.memory import delete_memory as api_delete
        result = await api_delete(memory.id, principal=p)
        assert result["ok"] is True

        reloaded = await repo.get_memory(p, memory.id)
        assert reloaded is not None
        await db_session.refresh(reloaded)
        assert reloaded.active is False

        outbox = await repo.list_outbox_for_memory(memory.id)
        delete_events = [o for o in outbox if o.operation == "DELETE"]
        assert len(delete_events) == 1
        assert delete_events[0].status == "PENDING"


# ---------------------------------------------------------------------------
# J. Semantic search with foreign conversation_id -> 404
# K. Corrupt Qdrant payload claims current user but canonical conversation memory
#    belongs to foreign user -> BLOCKED
# L. Owned conversation search -> PERSONAL + matching CONVERSATION work normally
# ---------------------------------------------------------------------------

class TestSemanticSearchConversationAuthorization:
    @pytest.mark.asyncio
    async def test_foreign_conversation_id_search_blocked(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_a)
        _make_user(db_session, user_b)
        await _commit(db_session)

        p_a = _principal(user_a, org_id)
        p_b = _principal(user_b, org_id)
        conv_a = _make_conv(db_session, org_id, user_a)
        conv_b = _make_conv(db_session, org_id, user_b)
        await _commit(db_session)

        memory_a = _make_memory(db_session, p_a, scope=MemoryScope.CONVERSATION.value, conversation_id=conv_a.id)
        _make_outbox(db_session, memory_a.id, operation=MemoryOutboxOperation.UPSERT.value)
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                await processor.run_batch()
            finally:
                await processor.close()

        # p_b searches with p_a's conversation_id -> must be blocked before Qdrant
        search = MemorySemanticSearch(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
        try:
            with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
                response = await search.search_memories(p_b, query="anything", conversation_id=conv_a.id)
            assert response.returned_count == 0
            assert response.candidate_count == 0
        finally:
            await search.close()

    @pytest.mark.asyncio
    async def test_corrupt_qdrant_payload_blocked_by_postgres(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_a)
        _make_user(db_session, user_b)
        await _commit(db_session)

        p_a = _principal(user_a, org_id)
        p_b = _principal(user_b, org_id)
        conv_a = _make_conv(db_session, org_id, user_a)
        conv_b = _make_conv(db_session, org_id, user_b)
        await _commit(db_session)

        # p_b owns a conversation memory
        memory_b = _make_memory(db_session, p_b, scope=MemoryScope.CONVERSATION.value, conversation_id=conv_b.id)
        _make_outbox(db_session, memory_b.id, operation=MemoryOutboxOperation.UPSERT.value)
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                await processor.run_batch()
            finally:
                await processor.close()

        # Corrupt Qdrant payload: claim p_b's memory belongs to p_a
        store = MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory")
        try:
            store.ensure_collection(expected_dim=384)
            # Directly upsert a point claiming p_b's memory belongs to p_a
            corrupt_payload = {
                "memory_id": memory_b.id,
                "content": memory_b.content,
                "organization_id": org_id,
                "user_id": user_a,  # corrupt: claims p_a owns it
                "conversation_id": conv_b.id,
                "scope": MemoryScope.CONVERSATION.value,
                "active": True,
            }
            store.upsert_point(memory_b.id, [0.1] * 384, corrupt_payload)
        finally:
            store.close()

        # p_a searches -> PostgreSQL must block because canonical memory belongs to p_b
        search = MemorySemanticSearch(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
        try:
            with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
                response = await search.search_memories(p_a, query="anything", conversation_id=conv_b.id)
            assert not any(r.memory_id == memory_b.id for r in response.results)
        finally:
            await search.close()

    @pytest.mark.asyncio
    async def test_owned_conversation_search_returns_personal_and_conversation(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = _make_conv(db_session, org_id, user_id)
        await _commit(db_session)

        personal_mem = _make_memory(db_session, p, scope=MemoryScope.PERSONAL.value, content="personal pref")
        conv_mem = _make_memory(db_session, p, scope=MemoryScope.CONVERSATION.value, conversation_id=conv.id, content="conv fact")
        _make_outbox(db_session, personal_mem.id, operation=MemoryOutboxOperation.UPSERT.value)
        _make_outbox(db_session, conv_mem.id, operation=MemoryOutboxOperation.UPSERT.value)
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                await processor.run_batch()
            finally:
                await processor.close()

        search = MemorySemanticSearch(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
        try:
            with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
                response = await search.search_memories(p, query="anything", conversation_id=conv.id)
            returned_ids = {r.memory_id for r in response.results}
            assert personal_mem.id in returned_ids
            assert conv_mem.id in returned_ids
        finally:
            await search.close()

    @pytest.mark.asyncio
    async def test_other_conversation_blocked_in_search(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv_a = _make_conv(db_session, org_id, user_id)
        conv_b = _make_conv(db_session, org_id, user_id)
        await _commit(db_session)

        conv_mem_b = _make_memory(db_session, p, scope=MemoryScope.CONVERSATION.value, conversation_id=conv_b.id, content="conv b fact")
        _make_outbox(db_session, conv_mem_b.id, operation=MemoryOutboxOperation.UPSERT.value)
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                await processor.run_batch()
            finally:
                await processor.close()

        search = MemorySemanticSearch(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
        try:
            with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
                response = await search.search_memories(p, query="anything", conversation_id=conv_a.id)
            assert not any(r.memory_id == conv_mem_b.id for r in response.results)
        finally:
            await search.close()
