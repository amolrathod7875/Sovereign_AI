import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import select

from app.config import settings
from app.identity.principal import Principal
from app.storage.postgres import (
    Base,
    Organization,
    User,
    OrganizationMembership,
    Conversation,
    Message,
    async_session,
)
import app.api.conversations as conversations_mod
import app.storage.postgres as postgres_mod
import app.context.builder as builder_mod

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
    original_conversations = conversations_mod.async_session
    original_builder = builder_mod.async_session
    postgres_mod.async_session = test_async_session
    conversations_mod.async_session = test_async_session
    builder_mod.async_session = test_async_session
    try:
        yield
    finally:
        postgres_mod.async_session = original_postgres
        conversations_mod.async_session = original_conversations
        builder_mod.async_session = original_builder


def _make_org(session, org_id: str, name: str = "Test Org") -> Organization:
    org = Organization(id=org_id, name=name)
    session.add(org)
    return org


def _make_user(session, user_id: str, display_name: str = "Test User") -> User:
    user = User(id=user_id, display_name=display_name)
    session.add(user)
    return user


def _make_membership(session, org_id: str, user_id: str, role: str = "member") -> OrganizationMembership:
    m = OrganizationMembership(organization_id=org_id, user_id=user_id, role=role, status="active")
    session.add(m)
    return m


def _principal(user_id: str, org_id: str, authenticated: bool = False) -> Principal:
    return Principal(user_id=user_id, organization_id=org_id, roles=["member"], authenticated=authenticated, source="test")


async def _commit(session: AsyncSession):
    await session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_conv(session: AsyncSession, org_id: str, user_id: str) -> Conversation:
    conv = Conversation(organization_id=org_id, owner_user_id=user_id, title="Test Conv")
    session.add(conv)
    await _commit(session)
    return conv


async def _add_msg(session: AsyncSession, conv_id: str, org_id: str, role: str, content: str, status: str = "OK", seq: int = None) -> Message:
    if seq is None:
        conv = await session.get(Conversation, conv_id)
        seq = conv.next_sequence_no
    conv = await session.get(Conversation, conv_id)
    conv.next_sequence_no = max(conv.next_sequence_no, seq + 1)
    msg = Message(
        conversation_id=conv_id,
        organization_id=org_id,
        sequence_no=seq,
        role=role,
        content=content,
        status=status,
    )
    session.add(msg)
    await _commit(session)
    return msg


# ---------------------------------------------------------------------------
# Context repository tests
# ---------------------------------------------------------------------------

class TestContextRepository:
    @pytest.mark.asyncio
    async def test_load_recent_messages_before_current(self, db_session: AsyncSession):
        from app.context.repository import load_conversation_messages
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv = await _create_conv(db_session, org_id, user_id)
        await _add_msg(db_session, conv.id, org_id, "user", "msg0", seq=0)
        await _add_msg(db_session, conv.id, org_id, "assistant", "msg1", seq=1)
        current = await _add_msg(db_session, conv.id, org_id, "user", "current", seq=2)
        await _add_msg(db_session, conv.id, org_id, "assistant", "msg3", seq=3)

        p = _principal(user_id, org_id)
        msgs = await load_conversation_messages(db_session, p, conv.id, before_sequence_no=current.sequence_no, limit=20)
        assert len(msgs) == 2
        assert msgs[0].sequence_no == 0
        assert msgs[0].content == "msg0"
        assert msgs[1].sequence_no == 1
        assert msgs[1].content == "msg1"

    @pytest.mark.asyncio
    async def test_respects_max_messages_limit(self, db_session: AsyncSession):
        from app.context.repository import load_conversation_messages
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv = await _create_conv(db_session, org_id, user_id)
        current = await _add_msg(db_session, conv.id, org_id, "user", "current", seq=20)
        for i in range(15):
            await _add_msg(db_session, conv.id, org_id, "user", f"msg{i}", seq=i)

        p = _principal(user_id, org_id)
        msgs = await load_conversation_messages(db_session, p, conv.id, before_sequence_no=current.sequence_no, limit=5)
        assert len(msgs) == 5
        assert msgs[0].sequence_no == 10

    @pytest.mark.asyncio
    async def test_returns_chronological_order(self, db_session: AsyncSession):
        from app.context.repository import load_conversation_messages
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv = await _create_conv(db_session, org_id, user_id)
        current = await _add_msg(db_session, conv.id, org_id, "user", "current", seq=3)
        await _add_msg(db_session, conv.id, org_id, "user", "first", seq=0)
        await _add_msg(db_session, conv.id, org_id, "assistant", "second", seq=1)
        await _add_msg(db_session, conv.id, org_id, "user", "third", seq=2)

        p = _principal(user_id, org_id)
        msgs = await load_conversation_messages(db_session, p, conv.id, before_sequence_no=current.sequence_no, limit=20)
        assert [m.content for m in msgs] == ["first", "second", "third"]
        assert [m.sequence_no for m in msgs] == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_excludes_empty_content_messages(self, db_session: AsyncSession):
        from app.context.repository import load_conversation_messages
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv = await _create_conv(db_session, org_id, user_id)
        current = await _add_msg(db_session, conv.id, org_id, "user", "current", seq=3)
        await _add_msg(db_session, conv.id, org_id, "user", "valid", seq=0)
        await _add_msg(db_session, conv.id, org_id, "assistant", "", seq=1)
        await _add_msg(db_session, conv.id, org_id, "user", "", seq=2)

        p = _principal(user_id, org_id)
        msgs = await load_conversation_messages(db_session, p, conv.id, before_sequence_no=current.sequence_no, limit=20)
        assert len(msgs) == 1
        assert msgs[0].content == "valid"


# ---------------------------------------------------------------------------
# Context builder tests
# ---------------------------------------------------------------------------

class TestContextBuilder:
    @pytest.mark.asyncio
    async def test_simple_context_includes_history(self, db_session: AsyncSession):
        from app.context.builder import build_conversation_context
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv = await _create_conv(db_session, org_id, user_id)
        current = await _add_msg(db_session, conv.id, org_id, "user", "What is my codename?", seq=2)
        await _add_msg(db_session, conv.id, org_id, "user", "My codename is Atlas.", seq=0)
        await _add_msg(db_session, conv.id, org_id, "assistant", "Understood.", seq=1)

        p = _principal(user_id, org_id)
        ctx, usage = await build_conversation_context(p, conv.id, current_message_id=current.id)
        assert usage.history_used is True
        assert usage.messages_included == 2
        assert usage.messages_considered == 2
        assert ctx.recent_messages[0].content == "My codename is Atlas."
        assert ctx.recent_messages[1].content == "Understood."

    @pytest.mark.asyncio
    async def test_current_message_excluded_from_history(self, db_session: AsyncSession):
        from app.context.builder import build_conversation_context
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv = await _create_conv(db_session, org_id, user_id)
        current = await _add_msg(db_session, conv.id, org_id, "user", "What codename?", seq=2)
        await _add_msg(db_session, conv.id, org_id, "user", "My codename is Atlas.", seq=0)
        await _add_msg(db_session, conv.id, org_id, "assistant", "Understood.", seq=1)

        p = _principal(user_id, org_id)
        ctx, usage = await build_conversation_context(p, conv.id, current_message_id=current.id)
        assert usage.messages_included == 2
        contents = [m.content for m in ctx.recent_messages]
        assert contents == ["My codename is Atlas.", "Understood."]
        assert "What codename?" not in contents

    @pytest.mark.asyncio
    async def test_no_conversation_id_no_context(self, db_session: AsyncSession):
        from app.context.builder import build_conversation_context
        p = _principal(str(uuid.uuid4()), str(uuid.uuid4()))
        ctx, usage = await build_conversation_context(p, None)
        assert usage.history_used is False
        assert usage.source == "none"
        assert len(ctx.recent_messages) == 0

    @pytest.mark.asyncio
    async def test_db_unavailable_graceful_fallback(self, db_session: AsyncSession):
        from app.context import builder as builder_mod
        original = builder_mod.async_session
        builder_mod.async_session = None
        try:
            p = _principal(str(uuid.uuid4()), str(uuid.uuid4()))
            ctx, usage = await builder_mod.build_conversation_context(p, "some-conv-id")
            assert usage.history_used is False
            assert usage.reason == "history_unavailable"
            assert usage.source == "none"
        finally:
            builder_mod.async_session = original

    @pytest.mark.asyncio
    async def test_unauthorized_different_user_404(self, db_session: AsyncSession):
        from app.context.builder import build_conversation_context
        org_id = str(uuid.uuid4())
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_a, "User A")
        _make_user(db_session, user_b, "User B")
        await _commit(db_session)

        conv = await _create_conv(db_session, org_id, user_a)
        current = await _add_msg(db_session, conv.id, org_id, "user", "secret", seq=1)

        p_b = _principal(user_b, org_id)
        with pytest.raises(Exception) as exc_info:
            await build_conversation_context(p_b, conv.id, current_message_id=current.id)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthorized_different_org_404(self, db_session: AsyncSession):
        from app.context.builder import build_conversation_context
        org_a = str(uuid.uuid4())
        org_b = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_a)
        _make_org(db_session, org_b)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv_a = await _create_conv(db_session, org_a, user_id)
        current = await _add_msg(db_session, conv_a.id, org_a, "user", "secret", seq=1)

        p_b = _principal(user_id, org_b)
        with pytest.raises(Exception) as exc_info:
            await build_conversation_context(p_b, conv_a.id, current_message_id=current.id)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_token_budget_truncation(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv = await _create_conv(db_session, org_id, user_id)
        current = await _add_msg(db_session, conv.id, org_id, "user", "current", seq=6)
        for i in range(5):
            content = "x" * 200  # ~50 tokens each
            await _add_msg(db_session, conv.id, org_id, "user", content, seq=i)

        p = _principal(user_id, org_id)
        from app.context.builder import build_conversation_context
        ctx, usage = await build_conversation_context(p, conv.id, current_message_id=current.id, token_budget=120)
        assert usage.truncated is True
        assert usage.messages_included < usage.messages_considered
        assert usage.messages_included == 2  # newest kept

    @pytest.mark.asyncio
    async def test_current_message_not_in_history(self, db_session: AsyncSession):
        from app.context.builder import build_conversation_context
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv = await _create_conv(db_session, org_id, user_id)
        current = await _add_msg(db_session, conv.id, org_id, "user", "current query", seq=1)
        await _add_msg(db_session, conv.id, org_id, "user", "old", seq=0)

        p = _principal(user_id, org_id)
        ctx, usage = await build_conversation_context(p, conv.id, current_message_id=current.id)
        contents = [m.content for m in ctx.recent_messages]
        assert "current query" not in contents
        assert contents == ["old"]

    @pytest.mark.asyncio
    async def test_chronological_order_preserved(self, db_session: AsyncSession):
        from app.context.builder import build_conversation_context
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv = await _create_conv(db_session, org_id, user_id)
        current = await _add_msg(db_session, conv.id, org_id, "user", "current", seq=5)
        await _add_msg(db_session, conv.id, org_id, "user", "a1", seq=0)
        await _add_msg(db_session, conv.id, org_id, "assistant", "a2", seq=1)
        await _add_msg(db_session, conv.id, org_id, "user", "a3", seq=2)
        await _add_msg(db_session, conv.id, org_id, "assistant", "a4", seq=3)
        await _add_msg(db_session, conv.id, org_id, "user", "a5", seq=4)

        p = _principal(user_id, org_id)
        ctx, usage = await build_conversation_context(p, conv.id, current_message_id=current.id)
        assert [m.content for m in ctx.recent_messages] == ["a1", "a2", "a3", "a4", "a5"]
        assert [m.sequence_no for m in ctx.recent_messages] == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_cross_conversation_isolation(self, db_session: AsyncSession):
        from app.context.builder import build_conversation_context
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv_a = await _create_conv(db_session, org_id, user_id)
        conv_b = await _create_conv(db_session, org_id, user_id)
        current_a = await _add_msg(db_session, conv_a.id, org_id, "user", "Atlas is secret", seq=1)
        current_b = await _add_msg(db_session, conv_b.id, org_id, "user", "What codename?", seq=1)

        p = _principal(user_id, org_id)
        ctx, usage = await build_conversation_context(p, conv_b.id, current_message_id=current_b.id)
        contents = [m.content for m in ctx.recent_messages]
        assert "Atlas is secret" not in contents
        assert usage.messages_included == 0

    @pytest.mark.asyncio
    async def test_empty_history_fresh_conversation(self, db_session: AsyncSession):
        from app.context.builder import build_conversation_context
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        conv = await _create_conv(db_session, org_id, user_id)
        current = await _add_msg(db_session, conv.id, org_id, "user", "first message", seq=0)

        p = _principal(user_id, org_id)
        ctx, usage = await build_conversation_context(p, conv.id, current_message_id=current.id)
        assert usage.history_used is False
        assert usage.messages_included == 0
        assert len(ctx.recent_messages) == 0
