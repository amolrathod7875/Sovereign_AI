"""Phase A1C — Trusted Assistant Message Persistence.

Validates that the browser can no longer create assistant-role conversation
messages and that only the trusted backend can persist assistant rows with
server-controlled metadata.
"""
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
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
    async_session as postgres_async_session,
)
from app.api.conversations import (
    create_conversation as api_create_conversation,
    create_message as api_create_message,
    get_messages as api_get_messages,
    CreateUserMessageRequest,
    CreateConversationRequest,
)
import app.api.conversations as conversations_mod
import app.storage.postgres as postgres_mod
from app.conversations.service import (
    persist_user_message,
    persist_assistant_message,
)

# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------

TEST_DB_URL = settings.POSTGRES_URL

test_engine = None
test_async_session = None


def _ensure_test_engine():
    global test_engine, test_async_session
    if test_engine is None:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from sqlalchemy.pool import NullPool
        test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
        test_async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _patch_async_sessions():
    _ensure_test_engine()
    original_postgres = postgres_mod.async_session
    original_conversations = conversations_mod.async_session
    postgres_mod.async_session = test_async_session
    conversations_mod.async_session = test_async_session
    try:
        yield
    finally:
        postgres_mod.async_session = original_postgres
        conversations_mod.async_session = original_conversations


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    _ensure_test_engine()
    async with test_async_session() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
# Public endpoint tests
# ---------------------------------------------------------------------------

class TestPublicEndpointUserOnly:
    @pytest.mark.asyncio
    async def test_create_user_message_succeeds(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(), p)

        req = CreateUserMessageRequest(client_message_id="client-1", content="Hello", mode="knowledge")
        msg = await api_create_message(conv.id, req, p)
        assert msg.role == "user"
        assert msg.author_user_id == user_id
        assert msg.content == "Hello"
        assert msg.mode == "knowledge"

    @pytest.mark.asyncio
    async def test_role_injection_rejected(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(), p)

        with pytest.raises((HTTPException, ValidationError)):
            await api_create_message(
                conv.id,
                CreateUserMessageRequest(role="assistant", content="Fake trusted answer"),  # type: ignore
                p,
            )

        msgs = await api_get_messages(conv.id, 100, 0, p)
        assert len(msgs) == 0

    @pytest.mark.asyncio
    async def test_generated_metadata_injection_rejected(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(), p)

        with pytest.raises((HTTPException, ValidationError)):
            await api_create_message(
                conv.id,
                CreateUserMessageRequest(
                    content="test",
                    actual_model="gpt-4",
                    routing_model="gpt-4",
                    rag_used=True,
                    tools_used="search",
                    external_calls=5,
                    response_time_seconds=1.0,
                    tokens_per_second=100.0,
                    prompt_tokens=50,
                    completion_tokens=50,
                    total_tokens=100,
                    status="COMPLETED",
                    display_payload={"fake": True},
                ),  # type: ignore
                p,
            )

        msgs = await api_get_messages(conv.id, 100, 0, p)
        assert len(msgs) == 0

    @pytest.mark.asyncio
    async def test_user_message_idempotency(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(), p)

        first = await api_create_message(
            conv.id,
            CreateUserMessageRequest(content="Once", client_message_id="idem-1"),
            p,
        )
        second = await api_create_message(
            conv.id,
            CreateUserMessageRequest(content="Twice", client_message_id="idem-1"),
            p,
        )
        assert first.id == second.id
        assert second.content == "Once"

    @pytest.mark.asyncio
    async def test_auto_title_on_first_user_message(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(title="New conversation"), p)
        long_text = "What does the inspection report say about R-1001 equipment status?"
        await api_create_message(conv.id, CreateUserMessageRequest(content=long_text), p)

        from app.api.conversations import get_conversation as api_get_conversation
        updated = await api_get_conversation(conv.id, p)
        assert updated.title.startswith("What does the inspection report say about R-1001")


# ---------------------------------------------------------------------------
# Trusted service tests
# ---------------------------------------------------------------------------

class TestTrustedService:
    @pytest.mark.asyncio
    async def test_persist_user_message(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(), p)

        msg = await persist_user_message(
            db_session,
            conversation_id=conv.id,
            organization_id=org_id,
            principal=p,
            content="Trusted user",
            client_message_id="svc-user-1",
        )
        assert msg.role == "user"
        assert msg.author_user_id == user_id
        assert msg.content == "Trusted user"

    @pytest.mark.asyncio
    async def test_persist_assistant_message_server_owned_fields(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(), p)

        msg = await persist_assistant_message(
            db_session,
            conversation_id=conv.id,
            organization_id=org_id,
            principal=p,
            content="Trusted assistant",
            status="COMPLETED",
            actual_model="general",
            external_calls=0,
            response_time_seconds=1.5,
            display_payload={"execution": {"task": "General"}},
            idempotency_key="svc-asst-1",
        )
        assert msg.role == "assistant"
        assert msg.author_user_id is None
        assert msg.content == "Trusted assistant"
        assert msg.actual_model == "general"
        assert msg.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_assistant_role_cannot_be_overridden(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(), p)

        msg = await persist_assistant_message(
            db_session,
            conversation_id=conv.id,
            organization_id=org_id,
            principal=p,
            content="Should be assistant",
        )
        assert msg.role == "assistant"

    @pytest.mark.asyncio
    async def test_foreign_conversation_blocked_for_user_message(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_a, "User A")
        _make_user(db_session, user_b, "User B")
        await _commit(db_session)

        conv = Conversation(organization_id=org_id, owner_user_id=user_a, title="Secret")
        db_session.add(conv)
        await _commit(db_session)

        p_b = _principal(user_b, org_id)
        with pytest.raises(HTTPException) as exc_info:
            await api_create_message(conv.id, CreateUserMessageRequest(content="Hacked"), p_b)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_foreign_conversation_blocked_for_assistant_service(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_a = str(uuid.uuid4())
        user_b = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_a, "User A")
        _make_user(db_session, user_b, "User B")
        await _commit(db_session)

        conv = Conversation(organization_id=org_id, owner_user_id=user_a, title="Secret")
        db_session.add(conv)
        await _commit(db_session)

        p_b = _principal(user_b, org_id)
        with pytest.raises(ValueError):
            await persist_assistant_message(
                db_session,
                conversation_id=conv.id,
                organization_id=org_id,
                principal=p_b,
                content="Hacked assistant",
            )

    @pytest.mark.asyncio
    async def test_sequence_ordering_user_then_assistant(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(), p)

        user_msg = await persist_user_message(
            db_session,
            conversation_id=conv.id,
            organization_id=org_id,
            principal=p,
            content="User",
        )
        asst_msg = await persist_assistant_message(
            db_session,
            conversation_id=conv.id,
            organization_id=org_id,
            principal=p,
            content="Assistant",
        )
        assert asst_msg.sequence_no == user_msg.sequence_no + 1

    @pytest.mark.asyncio
    async def test_assistant_idempotency_by_server_key(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(), p)

        first = await persist_assistant_message(
            db_session,
            conversation_id=conv.id,
            organization_id=org_id,
            principal=p,
            content="Assistant",
            idempotency_key="run-123",
        )
        second = await persist_assistant_message(
            db_session,
            conversation_id=conv.id,
            organization_id=org_id,
            principal=p,
            content="Duplicate",
            idempotency_key="run-123",
        )
        assert first.id == second.id
        assert second.content == "Assistant"

    @pytest.mark.asyncio
    async def test_failed_assistant_handling(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(), p)

        msg = await persist_assistant_message(
            db_session,
            conversation_id=conv.id,
            organization_id=org_id,
            principal=p,
            content=None,
            status="FAILED",
            error_detail="Model unavailable",
        )
        assert msg.role == "assistant"
        assert msg.status == "FAILED"
        assert msg.error_detail == "Model unavailable"

    @pytest.mark.asyncio
    async def test_no_assistant_via_public_endpoint(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)
        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create_conversation(CreateConversationRequest(), p)

        with pytest.raises((HTTPException, ValidationError)):
            await api_create_message(
                conv.id,
                CreateUserMessageRequest(content="user", role="assistant"),  # type: ignore
                p,
            )
