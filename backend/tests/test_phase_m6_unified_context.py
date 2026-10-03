"""Phase M6 — Unified memory-aware dynamic context tests."""
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
from app.context.unified_builder import build_unified_context, _build_memory_context
from app.context.schemas import UnifiedContextUsage
from app.storage.postgres import (
    Base,
    Organization,
    User,
    Conversation,
    ConversationMemory,
    MemoryProvenance,
    MemoryIndexOutbox,
    Message,
    async_session as _app_async_session,
)
import app.storage.postgres as postgres_mod
import app.memory.indexer as idx_mod
import app.memory.search as search_mod
import app.api.memory as memory_mod
import app.context.builder as builder_mod
import app.context.unified_builder as unified_mod

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
    original_builder = builder_mod.async_session
    original_unified = unified_mod.async_session
    postgres_mod.async_session = test_async_session
    idx_mod.async_session = test_async_session
    search_mod.async_session = test_async_session
    memory_mod.async_session = test_async_session
    builder_mod.async_session = test_async_session
    unified_mod.async_session = test_async_session
    try:
        yield
    finally:
        postgres_mod.async_session = original_postgres
        idx_mod.async_session = original_indexer
        search_mod.async_session = original_search
        memory_mod.async_session = original_memory
        builder_mod.async_session = original_builder
        unified_mod.async_session = original_unified


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
    await session.execute(sql_delete(MemoryIndexOutbox))
    await session.commit()


from app.memory.normalization import normalize_memory_content

# ... (keep the rest of imports)

async def _make_memory(
    session: AsyncSession,
    principal: Principal,
    content: str,
    scope: str = MemoryScope.PERSONAL.value,
    conversation_id: Optional[str] = None,
    memory_type: str = MemoryType.USER_PREFERENCE.value,
    importance: float = 0.8,
    confidence: float = 0.9,
    active: bool = True,
) -> ConversationMemory:
    memory = ConversationMemory(
        id=str(uuid.uuid4()),
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        conversation_id=conversation_id,
        scope=scope,
        memory_type=memory_type,
        content=content,
        normalized_content=normalize_memory_content(content),
        importance=importance,
        confidence=confidence,
        active=active,
        version=1,
    )
    session.add(memory)
    await session.flush()
    prov = MemoryProvenance(
        id=str(uuid.uuid4()),
        memory_id=memory.id,
        source_message_id=None,
        source_conversation_id=conversation_id,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
    )
    session.add(prov)
    outbox = MemoryIndexOutbox(
        id=str(uuid.uuid4()),
        memory_id=memory.id,
        operation=MemoryOutboxOperation.UPSERT.value,
        status=MemoryOutboxStatus.PENDING.value,
    )
    session.add(outbox)
    return memory


async def _index_memory_in_qdrant(memory: ConversationMemory, principal: Principal):
    """Index a canonical memory into local sovereign_memory for tests."""
    store = MemoryVectorStore()
    if not store.collection_exists():
        return
    from rag.models.embeddings import LocalEmbedder
    try:
        embedder = LocalEmbedder(settings.EMBEDDING_MODEL)
        vector = embedder.embed([memory.content])[0]
        store.upsert_point(
            memory_id=memory.id,
            vector=vector,
            payload={
                "memory_id": memory.id,
                "organization_id": principal.organization_id,
                "user_id": principal.user_id,
                "scope": memory.scope,
                "conversation_id": memory.conversation_id,
                "active": memory.active,
            },
        )
    except Exception:
        pass
    finally:
        store.close()


# ---------------------------------------------------------------------------
# M6 tests
# ---------------------------------------------------------------------------
class TestM6UnifiedContext:
    async def _setup_principal(self, db_session: AsyncSession) -> tuple[Principal, str, str]:
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id, f"Org {org_id[:8]}")
        _make_user(db_session, user_id, f"User {user_id[:8]}")
        await _commit(db_session)
        return _principal(user_id, org_id), org_id, user_id

    @pytest.mark.asyncio
    async def test_foreign_conversation_returns_404(self, db_session: AsyncSession):
        principal_a, org_a, user_a = await self._setup_principal(db_session)
        principal_b, org_b, user_b = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_b, user_b)
        await _commit(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await build_unified_context(
                principal=principal_a,
                task="hello",
                conversation_id=conv.id,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_personal_memory_injected(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="User prefers pressure values in bar.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        unified, usage = await build_unified_context(
            principal=principal,
            task="What pressure unit do I prefer?",
            conversation_id=conv.id,
        )
        assert usage.memory_used is True
        assert usage.memory_included_count >= 1
        assert mem.id in usage.memory_ids

    @pytest.mark.asyncio
    async def test_cross_conversation_personal_memory(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv_a = _make_conv(db_session, org_a, user_a)
        conv_b = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="User prefers pressure values in bar.",
            scope=MemoryScope.PERSONAL.value,
            conversation_id=conv_a.id,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        unified, usage = await build_unified_context(
            principal=principal,
            task="What pressure unit do I prefer?",
            conversation_id=conv_b.id,
        )
        assert usage.memory_used is True
        assert mem.id in usage.memory_ids

    @pytest.mark.asyncio
    async def test_conversation_memory_same_chat(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="Temporary codename is BLUE ORBIT.",
            scope=MemoryScope.CONVERSATION.value,
            conversation_id=conv.id,
            memory_type=MemoryType.CONVERSATION_FACT.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        unified, usage = await build_unified_context(
            principal=principal,
            task="What is our temporary codename?",
            conversation_id=conv.id,
        )
        assert usage.memory_used is True
        assert mem.id in usage.memory_ids

    @pytest.mark.asyncio
    async def test_other_conversation_memory_excluded(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv_a = _make_conv(db_session, org_a, user_a)
        conv_b = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="Temporary codename is RED COMET.",
            scope=MemoryScope.CONVERSATION.value,
            conversation_id=conv_a.id,
            memory_type=MemoryType.CONVERSATION_FACT.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        unified, usage = await build_unified_context(
            principal=principal,
            task="What is our temporary codename?",
            conversation_id=conv_b.id,
        )
        assert usage.memory_used is False
        assert mem.id not in usage.memory_ids

    @pytest.mark.asyncio
    async def test_foreign_user_memory_excluded(self, db_session: AsyncSession):
        principal_a, org_a, user_a = await self._setup_principal(db_session)
        # Create principal_b in the SAME org but different user
        user_b = str(uuid.uuid4())
        _make_user(db_session, user_b, f"User B {user_b[:8]}")
        await _commit(db_session)
        principal_b = _principal(user_b, org_a)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem_b = await _make_memory(
            db_session, principal_b,
            content="User prefers pressure values in psi.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem_b, principal_b)

        unified, usage = await build_unified_context(
            principal=principal_a,
            task="What pressure unit do I prefer?",
            conversation_id=conv.id,
        )
        assert usage.memory_used is False
        assert mem_b.id not in usage.memory_ids

    @pytest.mark.asyncio
    async def test_foreign_org_memory_excluded(self, db_session: AsyncSession):
        principal_a, org_a, user_a = await self._setup_principal(db_session)
        # Create a real foreign org and user
        foreign_org_id = str(uuid.uuid4())
        foreign_user_id = str(uuid.uuid4())
        _make_org(db_session, foreign_org_id, f"Foreign Org {foreign_org_id[:8]}")
        _make_user(db_session, foreign_user_id, f"Foreign User {foreign_user_id[:8]}")
        await _commit(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        # Create memory belonging to the foreign org directly
        foreign_principal = _principal(foreign_user_id, foreign_org_id)
        mem_foreign = await _make_memory(
            db_session, foreign_principal,
            content="Foreign org preference data.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        # Qdrant filter on org_id means this won't match principal_a's org
        unified, usage = await build_unified_context(
            principal=principal_a,
            task="Any foreign memory?",
            conversation_id=conv.id,
        )
        assert mem_foreign.id not in usage.memory_ids

    @pytest.mark.asyncio
    async def test_memory_not_in_system_role(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="User prefers pressure values in bar.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        unified, usage = await build_unified_context(
            principal=principal,
            task="What pressure unit do I prefer?",
            conversation_id=conv.id,
        )
        for msg in unified.model_messages:
            assert msg["role"] != "system" or "bar" not in msg["content"].lower()

    @pytest.mark.asyncio
    async def test_current_task_occurs_once(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="What pressure unit do I prefer?",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        task_text = "What pressure unit do I prefer?"
        unified, usage = await build_unified_context(
            principal=principal,
            task=task_text,
            conversation_id=conv.id,
        )
        count = sum(1 for m in unified.model_messages if task_text in m["content"])
        assert count == 1

    @pytest.mark.asyncio
    async def test_memory_duplicate_of_recent_blocked(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        # Add an earlier message that will be in recent history
        prev_msg = Message(
            conversation_id=conv.id,
            organization_id=org_a,
            author_user_id=user_a,
            role="user",
            content="User prefers pressure values in bar.",
            sequence_no=1,
            status="OK",
        )
        db_session.add(prev_msg)
        # Boundary message at sequence 2
        boundary_msg = Message(
            conversation_id=conv.id,
            organization_id=org_a,
            author_user_id=user_a,
            role="user",
            content="What pressure unit?",
            sequence_no=2,
            status="OK",
        )
        db_session.add(boundary_msg)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="User prefers pressure values in bar.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        unified, usage = await build_unified_context(
            principal=principal,
            task="What pressure unit?",
            conversation_id=conv.id,
            current_message_id=boundary_msg.id,
        )
        assert mem.id not in usage.memory_ids

    @pytest.mark.asyncio
    async def test_memory_duplicate_of_summary_blocked(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        # Add a message so summary has something to reference
        msg = Message(
            conversation_id=conv.id,
            organization_id=org_a,
            author_user_id=user_a,
            role="user",
            content="hello",
            sequence_no=1,
            status="OK",
        )
        db_session.add(msg)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="User prefers pressure values in bar.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)
        from app.context.summary_repository import upsert_summary
        record = await upsert_summary(
            db_session, principal, conv.id,
            summary_text="User prefers pressure values in bar.",
            summarized_through_sequence_no=0,
            source_message_count=0,
            estimated_tokens=10,
            model_id="general",
            new_version=1,
        )
        await _commit(db_session)

        unified, usage = await build_unified_context(
            principal=principal,
            task="What pressure unit do I prefer?",
            conversation_id=conv.id,
            current_message_id=msg.id,
        )
        assert mem.id not in usage.memory_ids

    @pytest.mark.asyncio
    async def test_model_message_ordering(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="User prefers pressure values in bar.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        unified, usage = await build_unified_context(
            principal=principal,
            task="What pressure unit?",
            conversation_id=conv.id,
        )
        roles = [m["role"] for m in unified.model_messages]
        assert roles[0] == "system"
        last_user_idx = next(i for i in range(len(roles) - 1, -1, -1) if roles[i] == "user")
        assert last_user_idx == len(roles) - 1

    @pytest.mark.asyncio
    async def test_unified_budget_not_exceeded(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        msg = Message(
            conversation_id=conv.id,
            organization_id=org_a,
            author_user_id=user_a,
            role="user",
            content="x" * 2000,
            sequence_no=1,
            status="OK",
        )
        db_session.add(msg)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="User prefers pressure values in bar.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        unified, usage = await build_unified_context(
            principal=principal,
            task="What pressure unit?",
            conversation_id=conv.id,
            current_message_id=msg.id,
        )
        assert usage.estimated_unified_tokens <= settings.UNIFIED_CONTEXT_TOKEN_BUDGET

    @pytest.mark.asyncio
    async def test_empty_memory_no_synthetic_block(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        unified, usage = await build_unified_context(
            principal=principal,
            task="Explain Python decorators.",
            conversation_id=conv.id,
        )
        assert usage.memory_used is False
        for msg in unified.model_messages:
            if msg["role"] == "assistant":
                assert "Long-term user memory context" not in msg.get("content", "")

    @pytest.mark.asyncio
    async def test_irrelevant_memory_below_threshold_not_injected(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="User prefers pressure values in bar.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        unified, usage = await build_unified_context(
            principal=principal,
            task="Explain Python decorators.",
            conversation_id=conv.id,
        )
        assert usage.memory_used is False

    @pytest.mark.asyncio
    async def test_current_request_overrides_memory(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="User prefers pressure values in bar.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        unified, usage = await build_unified_context(
            principal=principal,
            task="For this answer use psi instead.",
            conversation_id=conv.id,
        )
        assert usage.memory_used is True
        assert usage.memory_included_count >= 1

    @pytest.mark.asyncio
    async def test_project_organization_memory_not_enabled(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="Project fact for PROJECT scope.",
            scope=MemoryScope.PROJECT.value,
            memory_type=MemoryType.PROJECT_FACT.value,
        )
        await _commit(db_session)
        # Even if indexed, PROJECT should not be auto-searchable in M6
        unified, usage = await build_unified_context(
            principal=principal,
            task="Any project memory?",
            conversation_id=conv.id,
        )
        assert mem.id not in usage.memory_ids

    @pytest.mark.asyncio
    async def test_memory_search_unavailable_non_fatal(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        # Patch MemorySemanticSearch where it's imported in unified_builder
        with patch("app.context.unified_builder.MemorySemanticSearch", side_effect=Exception("Qdrant unavailable")):
            unified, usage = await build_unified_context(
                principal=principal,
                task="What is 2+2?",
                conversation_id=conv.id,
            )
        assert usage.memory_used is False
        assert usage.memory_reason == "memory_index_unavailable"

    @pytest.mark.asyncio
    async def test_no_conversation_id_no_memory_cross_leak(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="User prefers pressure values in bar.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)
        unified, usage = await build_unified_context(
            principal=principal,
            task="What pressure unit do I prefer?",
            conversation_id=None,
        )
        # Without conversation_id, only PERSONAL memory should be searchable
        assert usage.memory_used is True
        assert mem.id in usage.memory_ids

    @pytest.mark.asyncio
    async def test_budget_metadata_exposed(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        unified, usage = await build_unified_context(
            principal=principal,
            task="hello",
            conversation_id=conv.id,
        )
        assert usage.unified_context_budget == settings.UNIFIED_CONTEXT_TOKEN_BUDGET
        assert usage.estimated_unified_tokens >= 0
        assert usage.budget_remaining >= 0
        assert usage.estimated_unified_tokens <= usage.unified_context_budget

    @pytest.mark.asyncio
    async def test_raw_memory_not_in_metadata(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        mem = await _make_memory(
            db_session, principal,
            content="Sensitive secret preference data.",
            scope=MemoryScope.PERSONAL.value,
            memory_type=MemoryType.USER_PREFERENCE.value,
        )
        await _commit(db_session)
        await _index_memory_in_qdrant(mem, principal)

        unified, usage = await build_unified_context(
            principal=principal,
            task="What preference?",
            conversation_id=conv.id,
        )
        meta = {
            "memory_ids": usage.memory_ids,
            "memory_scopes": usage.memory_scopes,
            "memory_reason": usage.memory_reason,
        }
        assert "Sensitive secret preference data." not in str(meta)

    @pytest.mark.asyncio
    async def test_conversation_context_preserved(self, db_session: AsyncSession):
        principal, org_a, user_a = await self._setup_principal(db_session)
        conv = _make_conv(db_session, org_a, user_a)
        await _commit(db_session)
        msg = Message(
            conversation_id=conv.id,
            organization_id=org_a,
            author_user_id=user_a,
            role="user",
            content="hello",
            sequence_no=1,
            status="OK",
        )
        db_session.add(msg)
        await _commit(db_session)

        unified, usage = await build_unified_context(
            principal=principal,
            task="hello again",
            conversation_id=conv.id,
            current_message_id=msg.id,
        )
        assert unified.conversation_context is not None
        assert unified.conversation_context.conversation_id == conv.id
