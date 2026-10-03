"""Phase M5 — Semantic memory index tests."""
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
from sqlalchemy import select, text, or_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.identity.principal import Principal
from app.memory.schemas import MemoryOutboxOperation, MemoryOutboxStatus, MemoryScope, MemoryType
from app.memory.repository import MemoryRepository
from app.memory.vector_store import MemoryVectorStore, _stable_point_id
from app.memory.indexer import OutboxProcessor
from app.memory.search import MemorySemanticSearch, MemorySearchResponse
from app.memory.reconciliation import MemoryReconciliation, ReconciliationDelta
from app.storage.postgres import (
    Base,
    Organization,
    User,
    Conversation,
    ConversationMemory,
    MemoryIndexOutbox,
    async_session as _app_async_session,
)
import app.storage.postgres as postgres_mod
import app.memory.indexer as idx_mod
import app.memory.search as search_mod
import app.memory.reconciliation as recon_mod

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
    original_recon = recon_mod.async_session
    postgres_mod.async_session = test_async_session
    idx_mod.async_session = test_async_session
    search_mod.async_session = test_async_session
    recon_mod.async_session = test_async_session
    try:
        yield
    finally:
        postgres_mod.async_session = original_postgres
        idx_mod.async_session = original_indexer
        search_mod.async_session = original_search
        recon_mod.async_session = original_recon


def _principal(user_id: str, org_id: str) -> Principal:
    return Principal(user_id=user_id, organization_id=org_id, roles=["member"], authenticated=True, source="test")


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


async def _cleanup_org(session: AsyncSession, org_id: str):
    from sqlalchemy import delete
    await session.execute(delete(MemoryIndexOutbox).where(MemoryIndexOutbox.memory_id.in_(
        select(ConversationMemory.id).where(ConversationMemory.organization_id == org_id)
    )))
    await session.execute(delete(ConversationMemory).where(ConversationMemory.organization_id == org_id))
    await session.execute(delete(Conversation).where(Conversation.organization_id == org_id))
    await session.commit()


async def _cleanup_all_outbox(session: AsyncSession):
    from sqlalchemy import delete
    await session.execute(delete(MemoryIndexOutbox))
    await session.execute(delete(ConversationMemory))
    await session.commit()


async def _commit(session: AsyncSession):
    await session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DeterministicEmbedder:
    """Minimal deterministic embedder for tests."""

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


def _make_outbox(session: AsyncSession, memory_id: str, operation: str = MemoryOutboxOperation.UPSERT.value, status: str = MemoryOutboxStatus.PENDING.value) -> MemoryIndexOutbox:
    outbox = MemoryIndexOutbox(
        id=str(uuid.uuid4()),
        memory_id=memory_id,
        operation=operation,
        status=status,
    )
    session.add(outbox)
    return outbox


# ---------------------------------------------------------------------------
# Collection creation / dimension
# ---------------------------------------------------------------------------

class TestCollectionCreation:
    @pytest.mark.asyncio
    async def test_ensure_collection_creates_memory_collection(self, tmp_path: Path):
        store = MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory")
        try:
            store.ensure_collection(expected_dim=384)
            assert store.collection_exists()
            assert store._get_collection_dim() == 384
        finally:
            store.close()

    @pytest.mark.asyncio
    async def test_dimension_mismatch_raises(self, tmp_path: Path):
        store = MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory")
        try:
            store.ensure_collection(expected_dim=384)
            with pytest.raises(RuntimeError, match="dimension mismatch"):
                store.ensure_collection(expected_dim=768)
        finally:
            store.close()

    @pytest.mark.asyncio
    async def test_separate_memory_path_from_industrial_rag(self, tmp_path: Path):
        memory_path = tmp_path / "memory_db"
        rag_path = tmp_path / "rag_db"
        memory_store = MemoryVectorStore(path=str(memory_path), collection="sovereign_memory")
        try:
            memory_store.ensure_collection(expected_dim=384)
            assert memory_store.collection_exists()
        finally:
            memory_store.close()
        assert not rag_path.exists()


# ---------------------------------------------------------------------------
# Point identity / payload
# ---------------------------------------------------------------------------

class TestPointModel:
    def test_stable_point_id_from_uuid(self):
        memory_id = str(uuid.uuid4())
        assert _stable_point_id(memory_id) == memory_id

    def test_stable_point_id_fallback_uuid5(self):
        non_uuid = "memory:custom-id-123"
        point_id = _stable_point_id(non_uuid)
        assert _stable_point_id(non_uuid) == point_id

    @pytest.mark.asyncio
    async def test_upsert_and_delete_point(self, tmp_path: Path):
        store = MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory")
        try:
            store.ensure_collection(expected_dim=384)
            memory_id = str(uuid.uuid4())
            vector = [0.1] * 384
            payload = {"memory_id": memory_id, "content": "test"}
            store.upsert_point(memory_id, vector, payload)
            count_before = store.point_count()
            assert count_before == 1
            store.delete_point(memory_id)
            assert store.point_count() == 0
        finally:
            store.close()


# ---------------------------------------------------------------------------
# Outbox processor
# ---------------------------------------------------------------------------

class TestOutboxProcessor:
    @pytest.mark.asyncio
    async def test_upsert_active_memory(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)
        principal = _principal(user_id, org_id)
        memory = _make_memory(db_session, principal, active=True)
        _make_outbox(db_session, memory.id, operation=MemoryOutboxOperation.UPSERT.value)
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                summary = await processor.run_batch()
                assert summary["processed"] == 1
                assert summary["failed"] == 0
            finally:
                await processor.close()

    @pytest.mark.asyncio
    async def test_delete_inactive_memory(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)
        principal = _principal(user_id, org_id)
        memory = _make_memory(db_session, principal, active=False)
        _make_outbox(db_session, memory.id, operation=MemoryOutboxOperation.UPSERT.value)
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                summary = await processor.run_batch()
                assert summary["processed"] == 1
            finally:
                await processor.close()

    @pytest.mark.asyncio
    async def test_stale_upsert_canonical_state_wins(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)
        principal = _principal(user_id, org_id)
        memory = _make_memory(db_session, principal, active=True)
        _make_outbox(db_session, memory.id, operation=MemoryOutboxOperation.UPSERT.value)
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                summary = await processor.run_batch()
                assert summary["processed"] == 1
            finally:
                await processor.close()

        # Now deactivate memory (simulate stale UPSERT event still pending)
        async with test_async_session() as session:
            repo = MemoryRepository(session)
            m = await repo.get_memory(principal, memory.id)
            m.active = False
            session.add(m)
            _make_outbox(session, m.id, operation=MemoryOutboxOperation.UPSERT.value)
            await session.commit()

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                summary = await processor.run_batch()
                assert summary["processed"] == 1
            finally:
                await processor.close()

    @pytest.mark.asyncio
    async def test_idempotent_upsert_no_duplicate_point(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)
        principal = _principal(user_id, org_id)
        memory = _make_memory(db_session, principal, active=True)
        _make_outbox(db_session, memory.id, operation=MemoryOutboxOperation.UPSERT.value)
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                await processor.run_batch()
                await processor.run_batch()
            finally:
                await processor.close()

    @pytest.mark.asyncio
    async def test_idempotent_delete_no_error(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)
        principal = _principal(user_id, org_id)
        memory = _make_memory(db_session, principal, active=False)
        _make_outbox(db_session, memory.id, operation=MemoryOutboxOperation.DELETE.value)
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                await processor.run_batch()
                await processor.run_batch()
            finally:
                await processor.close()

    @pytest.mark.asyncio
    async def test_outbox_failure_increments_attempt(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)
        principal = _principal(user_id, org_id)
        memory = _make_memory(db_session, principal, active=True)
        outbox = _make_outbox(db_session, memory.id, operation=MemoryOutboxOperation.UPSERT.value)
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                with patch.object(processor, "_process_event", side_effect=RuntimeError("forced failure")):
                    summary = await processor.run_batch()
                assert summary["failed"] == 1
                async with test_async_session() as session:
                    result = await session.execute(select(MemoryIndexOutbox).where(MemoryIndexOutbox.id == outbox.id))
                    event = result.scalar_one()
                    assert event.status == MemoryOutboxStatus.FAILED.value
                    assert event.attempt_count == 1
            finally:
                await processor.close()

    @pytest.mark.asyncio
    async def test_retry_failed_event(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)
        principal = _principal(user_id, org_id)
        memory = _make_memory(db_session, principal, active=True)
        outbox = _make_outbox(db_session, memory.id, operation=MemoryOutboxOperation.UPSERT.value, status=MemoryOutboxStatus.FAILED.value)
        outbox.attempt_count = 1
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                summary = await processor.run_batch()
                assert summary["processed"] == 1
            finally:
                await processor.close()


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------

class TestSemanticSearch:
    @pytest.mark.asyncio
    async def test_search_returns_indexed_memory(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)
        principal = _principal(user_id, org_id)
        memory = _make_memory(db_session, principal, active=True, content="User prefers pressure measurements in bar.")
        _make_outbox(db_session, memory.id, operation=MemoryOutboxOperation.UPSERT.value)
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
                response = await search.search_memories(principal, query="What pressure unit should I use?")
            assert response.returned_count >= 1
            assert any(r.content == "User prefers pressure measurements in bar." for r in response.results)
        finally:
            await search.close()

    @pytest.mark.asyncio
    async def test_personal_cross_conversation_retrieval(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)
        principal = _principal(user_id, org_id)
        conv_a = _make_conv(db_session, org_id, user_id)
        conv_b = _make_conv(db_session, org_id, user_id)
        await _commit(db_session)
        memory = _make_memory(db_session, principal, active=True, content="User prefers pressure values in bar.", conversation_id=conv_a.id)
        _make_outbox(db_session, memory.id, operation=MemoryOutboxOperation.UPSERT.value)
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
                response = await search.search_memories(principal, query="What unit should pressure use?", conversation_id=conv_b.id)
            assert response.returned_count >= 1
        finally:
            await search.close()

    @pytest.mark.asyncio
    async def test_cross_user_isolation(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_a)
        _make_user(db_session, user_b)
        await _commit(db_session)
        principal_a = _principal(user_a, org_id)
        principal_b = _principal(user_b, org_id)
        memory_a = _make_memory(db_session, principal_a, active=True, content="User A prefers pressure in bar.")
        _make_outbox(db_session, memory_a.id, operation=MemoryOutboxOperation.UPSERT.value)
        memory_b = _make_memory(db_session, principal_b, active=True, content="User B prefers pressure in psi.")
        _make_outbox(db_session, memory_b.id, operation=MemoryOutboxOperation.UPSERT.value)
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
                resp_a = await search.search_memories(principal_a, query="preferred pressure unit")
            assert all(r.user_id != user_b for r in resp_a.results)
        finally:
            await search.close()

    @pytest.mark.asyncio
    async def test_postgres_stale_qdrant_blocked(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)
        principal = _principal(user_id, org_id)
        memory = _make_memory(db_session, principal, active=True)
        _make_outbox(db_session, memory.id, operation=MemoryOutboxOperation.UPSERT.value)
        await _commit(db_session)

        with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
            processor = OutboxProcessor(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
            try:
                await processor.run_batch()
            finally:
                await processor.close()

        # Simulate stale Qdrant payload with active=true but canonical inactive
        async with test_async_session() as session:
            repo = MemoryRepository(session)
            m = await repo.get_memory(principal, memory.id)
            m.active = False
            session.add(m)
            await session.commit()

        search = MemorySemanticSearch(store=MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory"))
        try:
            with patch("rag.models.embeddings.LocalEmbedder", DeterministicEmbedder):
                response = await search.search_memories(principal, query=memory.content)
            assert not any(r.memory_id == memory.id for r in response.results)
        finally:
            await search.close()

    @pytest.mark.asyncio
    async def test_search_score_order(self, db_session: AsyncSession, tmp_path: Path):
        await _cleanup_all_outbox(db_session)
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)
        principal = _principal(user_id, org_id)
        memory_relevant = _make_memory(db_session, principal, active=True, content="User prefers pressure measurements in bar.")
        memory_irrelevant = _make_memory(db_session, principal, active=True, content="The project uses Python.")
        _make_outbox(db_session, memory_relevant.id, operation=MemoryOutboxOperation.UPSERT.value)
        _make_outbox(db_session, memory_irrelevant.id, operation=MemoryOutboxOperation.UPSERT.value)
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
                response = await search.search_memories(principal, query="What pressure unit should I use?", top_k=2)
            assert response.returned_count >= 1
            scores = [r.semantic_score for r in response.results]
            assert scores == sorted(scores, reverse=True)
        finally:
            await search.close()


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

class TestReconciliation:
    @pytest.mark.asyncio
    async def test_orphan_detected(self, db_session: AsyncSession, tmp_path: Path):
        store = MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory")
        try:
            store.ensure_collection(expected_dim=384)
            orphan_id = str(uuid.uuid4())
            store.upsert_point(orphan_id, [0.0] * 384, {"memory_id": orphan_id, "content": "orphan"})
            reconciler = MemoryReconciliation(store=store)
            delta = await reconciler.diff()
            assert orphan_id in delta.orphan
        finally:
            store.close()

    @pytest.mark.asyncio
    async def test_repair_deletes_orphan(self, db_session: AsyncSession, tmp_path: Path):
        store = MemoryVectorStore(path=str(tmp_path / "qdrant_db"), collection="sovereign_memory")
        try:
            store.ensure_collection(expected_dim=384)
            orphan_id = str(uuid.uuid4())
            store.upsert_point(orphan_id, [0.0] * 384, {"memory_id": orphan_id, "content": "orphan"})
            reconciler = MemoryReconciliation(store=store)
            delta = await reconciler.diff()
            summary = await reconciler.repair(delta)
            assert summary["deleted"] >= 1
        finally:
            store.close()
