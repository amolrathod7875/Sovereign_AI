import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import select

from app.config import settings
from app.identity.principal import Principal, get_current_principal
from app.storage.postgres import (
    Base,
    Organization,
    User,
    OrganizationMembership,
    Conversation,
    Message,
    MessageAttachment,
    async_session,
    ensure_dev_principal,
)
import app.api.conversations as conversations_mod
import app.storage.postgres as postgres_mod
from app.conversations.service import persist_assistant_message

# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------

# Use the project database for integration tests. Alembic has already created
# the schema, so we do NOT call create_all here.
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
    """Force API code to use the isolated test engine/sessionmaker."""
    original_postgres = postgres_mod.async_session
    original_conversations = conversations_mod.async_session
    postgres_mod.async_session = test_async_session
    conversations_mod.async_session = test_async_session
    try:
        yield
    finally:
        postgres_mod.async_session = original_postgres
        conversations_mod.async_session = original_conversations


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
# Identity / principal tests
# ---------------------------------------------------------------------------

class TestPrincipal:
    def test_get_current_principal_returns_dev_principal(self):
        p = get_current_principal()
        assert p.organization_id == settings.SOVEREIGN_DEV_ORGANIZATION_ID
        assert p.user_id == settings.SOVEREIGN_DEV_USER_ID
        assert p.authenticated is False
        assert p.source == "local_development"

    def test_principal_dataclass(self):
        p = _principal("u1", "o1", authenticated=True)
        assert p.user_id == "u1"
        assert p.organization_id == "o1"
        assert p.roles == ["member"]
        assert p.authenticated is True
        assert p.source == "test"


# ---------------------------------------------------------------------------
# Isolation tests
# ---------------------------------------------------------------------------

class TestIsolation:
    @pytest.mark.asyncio
    async def test_same_user_can_access_own_conversation(self, db_session: AsyncSession):
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)

        await _commit(db_session)

        conv = Conversation(organization_id=org_id, owner_user_id=user_id, title="Test")
        db_session.add(conv)
        await _commit(db_session)

        from app.api.conversations import get_conversation as api_get_conversation
        p = _principal(user_id, org_id)
        result = await api_get_conversation(conv.id, p)
        assert result.id == conv.id

    @pytest.mark.asyncio
    async def test_different_user_blocked(self, db_session: AsyncSession):
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

        from app.api.conversations import get_conversation as api_get_conversation
        p_b = _principal(user_b, org_id)
        with pytest.raises(Exception) as exc_info:
            await api_get_conversation(conv.id, p_b)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_different_org_blocked(self, db_session: AsyncSession):
        org_a = str(uuid.uuid4())
        org_b = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_a)
        _make_org(db_session, org_b)
        _make_user(db_session, user_id)


        await _commit(db_session)

        conv_a = Conversation(organization_id=org_a, owner_user_id=user_id, title="Org A")
        db_session.add(conv_a)
        await _commit(db_session)

        from app.api.conversations import get_conversation as api_get_conversation
        p_b = _principal(user_id, org_b)
        with pytest.raises(Exception) as exc_info:
            await api_get_conversation(conv_a.id, p_b)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Conversation CRUD tests
# ---------------------------------------------------------------------------

class TestConversationCRUD:
    @pytest.mark.asyncio
    async def test_create_conversation(self, db_session: AsyncSession):
        from app.api.conversations import create_conversation as api_create
        from app.api.conversations import CreateConversationRequest
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)

        await _commit(db_session)

        p = _principal(user_id, org_id)
        result = await api_create(CreateConversationRequest(title="My Chat"), p)
        assert result.title == "My Chat"
        assert result.owner_user_id == user_id
        assert result.organization_id == org_id
        assert result.message_count == 0

    @pytest.mark.asyncio
    async def test_list_own_conversations(self, db_session: AsyncSession):
        from app.api.conversations import create_conversation as api_create, list_conversations as api_list
        from app.api.conversations import CreateConversationRequest
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)

        await _commit(db_session)

        p = _principal(user_id, org_id)
        await api_create(CreateConversationRequest(title="A"), p)
        await api_create(CreateConversationRequest(title="B"), p)

        results = await api_list(50, 0, p)
        assert len(results) == 2
        titles = {r.title for r in results}
        assert "A" in titles
        assert "B" in titles

    @pytest.mark.asyncio
    async def test_rename_conversation(self, db_session: AsyncSession):
        from app.api.conversations import create_conversation as api_create, update_conversation as api_update
        from app.api.conversations import CreateConversationRequest, UpdateConversationRequest
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)

        await _commit(db_session)

        p = _principal(user_id, org_id)
        created = await api_create(CreateConversationRequest(title="Old"), p)
        updated = await api_update(created.id, UpdateConversationRequest(title="New"), p)
        assert updated.title == "New"

    @pytest.mark.asyncio
    async def test_delete_conversation(self, db_session: AsyncSession):
        from app.api.conversations import create_conversation as api_create, delete_conversation as api_delete, get_conversation as api_get
        from app.api.conversations import CreateConversationRequest
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)

        await _commit(db_session)

        p = _principal(user_id, org_id)
        created = await api_create(CreateConversationRequest(), p)
        await api_delete(created.id, p)
        with pytest.raises(Exception) as exc_info:
            await api_get(created.id, p)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Message tests
# ---------------------------------------------------------------------------

class TestMessages:
    @pytest.mark.asyncio
    async def test_create_and_list_messages(self, db_session: AsyncSession):
        from app.api.conversations import (
            create_conversation as api_create,
            get_messages as api_msgs,
            create_message as api_msg,
        )
        from app.api.conversations import CreateConversationRequest, CreateUserMessageRequest
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)

        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create(CreateConversationRequest(), p)

        await api_msg(conv.id, CreateUserMessageRequest(content="Hello"), p)
        await persist_assistant_message(
            db_session,
            conversation_id=conv.id,
            organization_id=org_id,
            principal=p,
            content="Hi there",
        )

        msgs = await api_msgs(conv.id, 100, 0, p)
        assert len(msgs) == 2
        assert msgs[0].content == "Hello"
        assert msgs[0].sequence_no == 0
        assert msgs[1].content == "Hi there"
        assert msgs[1].sequence_no == 1

    @pytest.mark.asyncio
    async def test_client_message_id_idempotency(self, db_session: AsyncSession):
        from app.api.conversations import (
            create_conversation as api_create,
            create_message as api_msg,
        )
        from app.api.conversations import CreateConversationRequest, CreateUserMessageRequest
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)

        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create(CreateConversationRequest(), p)

        cid = "client-123"
        first = await api_msg(conv.id, CreateUserMessageRequest(content="Once", client_message_id=cid), p)
        second = await api_msg(conv.id, CreateUserMessageRequest(content="Twice", client_message_id=cid), p)
        assert first.id == second.id
        assert second.content == "Once"  # original content preserved

    @pytest.mark.asyncio
    async def test_auto_title_on_first_message(self, db_session: AsyncSession):
        from app.api.conversations import (
            create_conversation as api_create,
            create_message as api_msg,
            get_conversation as api_get,
        )
        from app.api.conversations import CreateConversationRequest, CreateUserMessageRequest
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)

        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create(CreateConversationRequest(title="New conversation"), p)
        long_text = "What does the inspection report say about R-1001 equipment status?"
        await api_msg(conv.id, CreateUserMessageRequest(content=long_text), p)

        updated = await api_get(conv.id, p)
        assert updated.title.startswith("What does the inspection report say about R-1001")

    @pytest.mark.asyncio
    async def test_message_order_uniqueness(self, db_session: AsyncSession):
        from app.api.conversations import (
            create_conversation as api_create,
            create_message as api_msg,
            get_messages as api_msgs,
        )
        from app.api.conversations import CreateConversationRequest, CreateUserMessageRequest
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)

        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create(CreateConversationRequest(), p)
        for i in range(5):
            await api_msg(conv.id, CreateUserMessageRequest(content=f"Msg {i}"), p)

        msgs = await api_msgs(conv.id, 100, 0, p)
        assert [m.sequence_no for m in msgs] == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_cascade_delete_messages(self, db_session: AsyncSession):
        from app.api.conversations import (
            create_conversation as api_create,
            create_message as api_msg,
            delete_conversation as api_delete,
        )
        from app.api.conversations import CreateConversationRequest, CreateUserMessageRequest
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        _make_org(db_session, org_id)
        _make_user(db_session, user_id)

        await _commit(db_session)

        p = _principal(user_id, org_id)
        conv = await api_create(CreateConversationRequest(), p)
        await api_msg(conv.id, CreateUserMessageRequest(content="Delete me"), p)
        await api_delete(conv.id, p)

        count = await db_session.execute(select(Message).where(Message.conversation_id == conv.id))
        assert count.scalars().first() is None


# ---------------------------------------------------------------------------
# Postgres-unavailable test
# ---------------------------------------------------------------------------

class TestPostgresUnavailable:
    @pytest.mark.asyncio
    async def test_503_when_no_session(self):
        from app.api.conversations import _check_db
        original = conversations_mod.async_session
        conversations_mod.async_session = None
        try:
            with pytest.raises(Exception) as exc_info:
                await _check_db()
            assert exc_info.value.status_code == 503
        finally:
            conversations_mod.async_session = original


# ---------------------------------------------------------------------------
# Dev principal bootstrap test
# ---------------------------------------------------------------------------

class TestDevPrincipalBootstrap:
    @pytest.mark.asyncio
    async def test_ensure_dev_principal_creates_org_user_membership(self, db_session: AsyncSession):
        # Use unique IDs to avoid collision with existing dev principal
        settings.SOVEREIGN_DEV_ORGANIZATION_ID = str(uuid.uuid4())
        settings.SOVEREIGN_DEV_USER_ID = str(uuid.uuid4())
        settings.SOVEREIGN_DEV_DISPLAY_NAME = "Test Dev User"

        await ensure_dev_principal()
        await _commit(db_session)

        org = await db_session.get(Organization, settings.SOVEREIGN_DEV_ORGANIZATION_ID)
        user = await db_session.get(User, settings.SOVEREIGN_DEV_USER_ID)
        assert org is not None
        assert user is not None
        assert org.name == "Local Development Organization"
        assert user.display_name == "Test Dev User"

        membership = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == settings.SOVEREIGN_DEV_ORGANIZATION_ID,
                OrganizationMembership.user_id == settings.SOVEREIGN_DEV_USER_ID,
            )
        )
        m = membership.scalar_one_or_none()
        assert m is not None
        assert m.role == "owner"
