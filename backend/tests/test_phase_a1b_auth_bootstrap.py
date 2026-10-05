"""Phase A1B — Auth bootstrap + public auth config tests.

Verifies:
  GET /api/auth/config   (PUBLIC — no token required)
  GET /api/auth/bootstrap (TOKEN_ONLY — valid JWT required, no org header)
"""
from __future__ import annotations

import json
import uuid
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import pytest
import pytest_asyncio
import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.identity.principal import Principal, get_dev_principal
from app.storage.postgres import (
    Base,
    Organization,
    User,
    OrganizationMembership,
    async_session as _global_async_session,
    init_db,
)
from app.main import app as _fastapi_app
import app.storage.postgres as postgres_mod
import app.api.conversations as conversations_mod
import app.api.memory as memory_mod
import app.api.general as general_mod
import app.context.unified_builder as unified_mod
import app.context.builder as builder_mod
import app.auth.jwt_validator as jwt_validator_mod

# ---------------------------------------------------------------------------
# Test database
# ---------------------------------------------------------------------------

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
    original_conversations = getattr(conversations_mod, "async_session", None)
    original_memory = getattr(memory_mod, "async_session", None)
    original_unified = getattr(unified_mod, "async_session", None)
    original_builder = getattr(builder_mod, "async_session", None)

    postgres_mod.async_session = test_async_session
    if original_conversations is not None:
        conversations_mod.async_session = test_async_session
    if original_memory is not None:
        memory_mod.async_session = test_async_session
    if original_unified is not None:
        unified_mod.async_session = test_async_session
    if original_builder is not None:
        builder_mod.async_session = test_async_session

    try:
        yield
    finally:
        postgres_mod.async_session = original_postgres
        if original_conversations is not None:
            conversations_mod.async_session = original_conversations
        if original_memory is not None:
            memory_mod.async_session = original_memory
        if original_unified is not None:
            unified_mod.async_session = original_unified
        if original_builder is not None:
            builder_mod.async_session = original_builder


# ---------------------------------------------------------------------------
# RSA/JWT helpers
# ---------------------------------------------------------------------------


def _generate_rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _private_key_to_pem(private_key: rsa.RSAPrivateKey) -> str:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def _int_to_base64url(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    import base64
    return base64.urlsafe_b64encode(value.to_bytes(length, byteorder="big")).rstrip(b"=").decode("ascii")


def _public_key_to_jwk(public_key: rsa.RSAPublicKey, kid: str, alg: str = "RS256") -> Dict[str, Any]:
    numbers = public_key.public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "alg": alg,
        "use": "sig",
        "n": _int_to_base64url(numbers.n),
        "e": _int_to_base64url(numbers.e),
    }


def _build_jwks(public_key: rsa.RSAPublicKey, kid: str) -> Dict[str, Any]:
    return {"keys": [_public_key_to_jwk(public_key, kid)]}


def _sign_token(
    private_key: rsa.RSAPrivateKey,
    subject: str,
    issuer: str,
    audience: str,
    kid: str = "test-key-1",
    expiry_seconds: int = 3600,
    not_before: Optional[Any] = None,
) -> str:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expiry_seconds)).timestamp()),
    }
    if not_before is not None:
        payload["nbf"] = int(not_before.timestamp())
    return pyjwt.encode(
        payload,
        _private_key_to_pem(private_key),
        algorithm="RS256",
        headers={"kid": kid},
    )


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _create_org(session, org_id: Optional[str] = None, name: str = "Test Org") -> Organization:
    org = Organization(id=org_id or str(uuid.uuid4()), name=name)
    session.add(org)
    return org


def _create_user(
    session,
    user_id: Optional[str] = None,
    display_name: str = "Test User",
    external_subject: Optional[str] = None,
    email: Optional[str] = None,
    active: bool = True,
) -> User:
    user = User(
        id=user_id or str(uuid.uuid4()),
        display_name=display_name,
        external_subject=external_subject,
        email=email,
        active=active,
    )
    session.add(user)
    return user


def _create_membership(
    session,
    org_id: str,
    user_id: str,
    role: str = "member",
    status: str = "active",
) -> OrganizationMembership:
    m = OrganizationMembership(organization_id=org_id, user_id=user_id, role=role, status=status)
    session.add(m)
    return m


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    return TestClient(_fastapi_app)


@pytest.fixture
def development_client(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "development")
    return TestClient(_fastapi_app)


@pytest.fixture
def jwks_file(tmp_path: Path, rsa_keypair) -> Path:
    _, public_key = rsa_keypair
    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(json.dumps(_build_jwks(public_key, "test-key-1")), encoding="utf-8")
    return jwks_path


@pytest.fixture
def rsa_keypair():
    private_key, public_key = _generate_rsa_keypair()
    return private_key, public_key


@pytest.fixture
def unique_subject():
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def oidc_client(jwks_file, rsa_keypair, monkeypatch):
    private_key, _ = rsa_keypair
    issuer = "http://localhost/sovereign-test-idp"
    audience = "sovereign-ai-test"

    monkeypatch.setattr(settings, "AUTH_MODE", "oidc")
    monkeypatch.setattr(settings, "OIDC_ISSUER", issuer)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", audience)
    monkeypatch.setattr(settings, "OIDC_JWKS_FILE", str(jwks_file))
    monkeypatch.setattr(settings, "OIDC_JWKS_URL", "")
    monkeypatch.setattr(settings, "OIDC_ALLOWED_ALGORITHMS", "RS256")
    monkeypatch.setattr(settings, "OIDC_CLOCK_SKEW_SECONDS", 30)
    monkeypatch.setattr(settings, "OIDC_JWKS_CACHE_TTL_SECONDS", 600)
    monkeypatch.setattr(settings, "OIDC_CLIENT_ID", "test-client")
    monkeypatch.setattr(settings, "OIDC_FRONTEND_SCOPES", "openid profile email")

    # Reset JWT validator cache so it picks up the new JWKS file.
    jwt_validator_mod.jwt_validator._jwks = None
    jwt_validator_mod.jwt_validator._jwks_loaded_at = 0.0

    yield TestClient(_fastapi_app)

    monkeypatch.setattr(settings, "AUTH_MODE", "development")
    monkeypatch.setattr(settings, "OIDC_ISSUER", "")
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", "")
    jwt_validator_mod.jwt_validator._jwks = None
    jwt_validator_mod.jwt_validator._jwks_loaded_at = 0.0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAuthConfigPublic:
    @pytest.mark.asyncio
    async def test_config_public_no_token(self, client):
        response = client.get("/api/auth/config")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_config_development_mode(self, development_client):
        response = development_client.get("/api/auth/config")
        assert response.status_code == 200
        data = response.json()
        assert data["auth_mode"] == "development"
        assert data["authentication_required"] is False
        assert data["oidc"] is None

    @pytest.mark.asyncio
    async def test_config_oidc_mode_configured(self, oidc_client):
        response = oidc_client.get("/api/auth/config")
        assert response.status_code == 200
        data = response.json()
        assert data["auth_mode"] == "oidc"
        assert data["authentication_required"] is True
        assert data["oidc"] is not None
        assert data["oidc"]["client_id"] == "test-client"
        assert "authority" in data["oidc"]
        assert "scope" in data["oidc"]

    @pytest.mark.asyncio
    async def test_config_no_secret_exposed(self, oidc_client):
        response = oidc_client.get("/api/auth/config")
        assert response.status_code == 200
        text = response.text.lower()
        assert "secret" not in text
        assert "password" not in text
        assert "private" not in text
        assert "postgres" not in text
        assert "jwks_file" not in text


class TestAuthBootstrapTokenOnly:
    @pytest.mark.asyncio
    async def test_bootstrap_no_token_returns_401(self, oidc_client):
        response = oidc_client.get("/api/auth/bootstrap")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_bootstrap_invalid_token_returns_401(self, oidc_client):
        response = oidc_client.get("/api/auth/bootstrap", headers={"Authorization": "Bearer invalid-token"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_bootstrap_unknown_user_returns_403(
        self, oidc_client, db_session, rsa_keypair, unique_subject
    ):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/bootstrap", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_bootstrap_inactive_user_returns_403(
        self, oidc_client, db_session, rsa_keypair, unique_subject
    ):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org = _create_org(db_session, name="Test Org")
        await db_session.flush()
        user = _create_user(db_session, display_name="Inactive User", external_subject=canonical_key, active=False)
        await db_session.flush()
        _create_membership(db_session, org.id, user.id, role="member")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/bootstrap", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_bootstrap_zero_memberships_returns_403(
        self, oidc_client, db_session, rsa_keypair, unique_subject
    ):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        user = _create_user(db_session, display_name="No-Member User", external_subject=canonical_key)
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/bootstrap", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_bootstrap_single_membership_returns_200(
        self, oidc_client, db_session, rsa_keypair, unique_subject
    ):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org = _create_org(db_session, name="Single Org")
        await db_session.flush()
        user = _create_user(db_session, display_name="Single Member", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org.id, user.id, role="owner")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/bootstrap", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["user_id"] == user.id
        assert data["user"]["display_name"] == "Single Member"
        assert len(data["memberships"]) == 1
        assert data["memberships"][0]["organization_id"] == org.id
        assert data["memberships"][0]["organization_name"] == "Single Org"
        assert data["memberships"][0]["role"] == "owner"

    @pytest.mark.asyncio
    async def test_bootstrap_multiple_memberships_returns_200(
        self, oidc_client, db_session, rsa_keypair, unique_subject
    ):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org_a = _create_org(db_session, name="Org A")
        org_b = _create_org(db_session, name="Org B")
        await db_session.flush()
        user = _create_user(db_session, display_name="Multi Member", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org_a.id, user.id, role="member")
        _create_membership(db_session, org_b.id, user.id, role="admin")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/bootstrap", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert len(data["memberships"]) == 2
        org_ids = {m["organization_id"] for m in data["memberships"]}
        assert org_a.id in org_ids
        assert org_b.id in org_ids

    @pytest.mark.asyncio
    async def test_bootstrap_no_org_header_required(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org = _create_org(db_session, name="No Header Org")
        await db_session.flush()
        user = _create_user(db_session, display_name="No Header User", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org.id, user.id, role="member")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        # Deliberately omit X-Sovereign-Organization
        response = oidc_client.get(
            "/api/auth/bootstrap",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


class TestAuthBootstrapSecurity:
    @pytest.mark.asyncio
    async def test_bootstrap_does_not_expose_secrets(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org = _create_org(db_session, name="Secure Org")
        await db_session.flush()
        user = _create_user(db_session, display_name="Secure User", external_subject=canonical_key, email="user@test")
        await db_session.flush()
        _create_membership(db_session, org.id, user.id, role="member")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/bootstrap", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert "external_subject" not in data["user"]
        assert "issuer" not in data
        assert "tokens" not in data
        assert "secret" not in json.dumps(data).lower()
