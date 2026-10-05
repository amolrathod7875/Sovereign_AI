"""A1A enterprise authentication core tests."""
from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
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
from sqlalchemy import select

from app.config import settings
from app.identity.principal import Principal, get_dev_principal
from app.storage.postgres import (
    Base,
    Organization,
    User,
    OrganizationMembership,
    Conversation,
    Message,
    async_session as _global_async_session,
    init_db,
)
from app.main import app as _fastapi_app
import app.storage.postgres as postgres_mod

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
    postgres_mod.async_session = test_async_session
    try:
        yield
    finally:
        postgres_mod.async_session = original_postgres


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


def _public_key_to_pem(public_key: rsa.RSAPublicKey) -> str:
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def _int_to_base64url(value: int) -> str:
    length = (value.bit_length() + 7) // 8
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
    kid: str,
    alg: str = "RS256",
    expiry_seconds: int = 3600,
    not_before: Optional[datetime] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expiry_seconds)).timestamp()),
    }
    if not_before:
        payload["nbf"] = int(not_before.timestamp())
    if extra_claims:
        payload.update(extra_claims)
    return pyjwt.encode(payload, _private_key_to_pem(private_key), algorithm=alg, headers={"kid": kid})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def unique_subject():
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def rsa_keypair():
    private_key, public_key = _generate_rsa_keypair()
    return private_key, public_key


@pytest.fixture
def jwks_file(tmp_path: Path, rsa_keypair) -> Path:
    _, public_key = rsa_keypair
    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(json.dumps(_build_jwks(public_key, "test-key-1")), encoding="utf-8")
    return jwks_path


@pytest.fixture
def client():
    yield TestClient(_fastapi_app)


@pytest.fixture
def oidc_client(jwks_file, rsa_keypair, monkeypatch):
    import sys
    import app.auth.jwt_validator as jwt_validator_mod
    jwt_validator_mod = sys.modules['app.auth.jwt_validator']

    private_key, _ = rsa_keypair
    issuer = "http://localhost/sovereign-test-idp"
    audience = "sovereign-ai-test"
    kid = "test-key-1"

    monkeypatch.setattr(settings, "AUTH_MODE", "oidc")
    monkeypatch.setattr(settings, "OIDC_ISSUER", issuer)
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", audience)
    monkeypatch.setattr(settings, "OIDC_JWKS_FILE", str(jwks_file))
    monkeypatch.setattr(settings, "OIDC_ALLOWED_ALGORITHMS", "RS256")
    monkeypatch.setattr(settings, "OIDC_CLOCK_SKEW_SECONDS", 30)
    monkeypatch.setattr(settings, "OIDC_JWKS_CACHE_TTL_SECONDS", 600)

    jwt_validator_mod.jwt_validator._jwks = None
    jwt_validator_mod.jwt_validator._jwks_loaded_at = 0.0

    yield TestClient(_fastapi_app)

    monkeypatch.setattr(settings, "AUTH_MODE", "development")
    monkeypatch.setattr(settings, "OIDC_ISSUER", "")
    monkeypatch.setattr(settings, "OIDC_AUDIENCE", "")
    monkeypatch.setattr(settings, "OIDC_JWKS_FILE", "")
    jwt_validator_mod.jwt_validator._jwks = None
    jwt_validator_mod.jwt_validator._jwks_loaded_at = 0.0


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _create_org(session, org_id: Optional[str] = None, name: str = "Test Org") -> Organization:
    org = Organization(id=org_id or str(uuid.uuid4()), name=name)
    session.add(org)
    return org


def _create_user(session, user_id: Optional[str] = None, display_name: str = "Test User", external_subject: Optional[str] = None, email: Optional[str] = None, active: bool = True) -> User:
    user = User(
        id=user_id or str(uuid.uuid4()),
        display_name=display_name,
        external_subject=external_subject,
        email=email,
        active=active,
    )
    session.add(user)
    return user


def _create_membership(session, org_id: str, user_id: str, role: str = "member", status: str = "active") -> OrganizationMembership:
    m = OrganizationMembership(organization_id=org_id, user_id=user_id, role=role, status=status)
    session.add(m)
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDevelopmentMode:
    @pytest.mark.asyncio
    async def test_dev_principal(self, client):
        response = client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["source"] == "local_development"
        assert data["user_id"] == settings.SOVEREIGN_DEV_USER_ID


class TestOIDCMode:
    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self, oidc_client):
        response = oidc_client.get("/api/auth/me")
        assert response.status_code == 401
        assert response.headers.get("www-authenticate", "").lower() == "bearer"

    @pytest.mark.asyncio
    async def test_valid_token_returns_200(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org = _create_org(db_session, name="Test Org")
        await db_session.flush()
        user = _create_user(db_session, display_name="OIDC User", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org.id, user.id, role="member")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["source"] == "oidc"
        assert data["user_id"] == user.id
        assert data["organization_id"] == org.id
        assert data["roles"] == ["member"]

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self, oidc_client, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        token = _sign_token(private_key, unique_subject, issuer, audience, "test-key-1", expiry_seconds=-120)
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_future_nbf_returns_401(self, oidc_client, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        now = datetime.now(timezone.utc)
        nbf = now + timedelta(minutes=5)
        token = _sign_token(private_key, unique_subject, issuer, audience, "test-key-1", not_before=nbf)
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_issuer_returns_401(self, oidc_client, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        token = _sign_token(private_key, unique_subject, "wrong-issuer", settings.OIDC_AUDIENCE, "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_audience_returns_401(self, oidc_client, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        token = _sign_token(private_key, unique_subject, settings.OIDC_ISSUER, "wrong-audience", "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_sub_returns_401(self, oidc_client, rsa_keypair):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        now = datetime.now(timezone.utc)
        payload = {
            "iss": issuer,
            "aud": audience,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=3600)).timestamp()),
        }
        token = pyjwt.encode(payload, _private_key_to_pem(private_key), algorithm="RS256", headers={"kid": "test-key-1"})
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_alg_none_rejected(self, oidc_client, unique_subject):
        payload = {
            "sub": unique_subject,
            "iss": settings.OIDC_ISSUER,
            "aud": settings.OIDC_AUDIENCE,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = pyjwt.encode(payload, "", algorithm="none")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_subject_returns_403(self, oidc_client, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = f"unknown-{unique_subject}"
        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_inactive_user_returns_403(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = f"inactive-{unique_subject}"
        canonical_key = f"{issuer}|{subject}"

        org = _create_org(db_session, name="Test Org")
        await db_session.flush()
        user = _create_user(db_session, display_name="Inactive User", external_subject=canonical_key, active=False)
        await db_session.flush()
        _create_membership(db_session, org.id, user.id)
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_no_membership_returns_403(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = f"no-membership-{unique_subject}"
        canonical_key = f"{issuer}|{subject}"

        user = _create_user(db_session, display_name="No Membership", external_subject=canonical_key)
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_inactive_membership_returns_403(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = f"inactive-membership-{unique_subject}"
        canonical_key = f"{issuer}|{subject}"

        org = _create_org(db_session, name="Test Org")
        await db_session.flush()
        user = _create_user(db_session, display_name="Inactive Membership", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org.id, user.id, status="inactive")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_multi_org_without_header_returns_409(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = f"multi-org-{unique_subject}"
        canonical_key = f"{issuer}|{subject}"

        org1 = _create_org(db_session, name="Org 1")
        await db_session.flush()
        org2 = _create_org(db_session, name="Org 2")
        await db_session.flush()
        user = _create_user(db_session, display_name="Multi Org", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org1.id, user.id)
        await db_session.flush()
        _create_membership(db_session, org2.id, user.id)
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_multi_org_with_valid_header_returns_200(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = f"multi-org-2-{unique_subject}"
        canonical_key = f"{issuer}|{subject}"

        org1 = _create_org(db_session, name="Org 1")
        await db_session.flush()
        org2 = _create_org(db_session, name="Org 2")
        await db_session.flush()
        user = _create_user(db_session, display_name="Multi Org 2", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org1.id, user.id)
        await db_session.flush()
        _create_membership(db_session, org2.id, user.id)
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}", settings.AUTH_ORGANIZATION_HEADER: org2.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["organization_id"] == org2.id

    @pytest.mark.asyncio
    async def test_foreign_org_header_returns_403(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = f"foreign-org-{unique_subject}"
        canonical_key = f"{issuer}|{subject}"

        org1 = _create_org(db_session, name="Org 1")
        await db_session.flush()
        foreign_org_id = str(uuid.uuid4())
        user = _create_user(db_session, display_name="Foreign Org", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org1.id, user.id)
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        # Single membership: supplied foreign organization header must be rejected.
        response = oidc_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}", settings.AUTH_ORGANIZATION_HEADER: foreign_org_id},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_single_membership_no_header_selects_org(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org = _create_org(db_session, name="Org A")
        await db_session.flush()
        user = _create_user(db_session, display_name="Single Org User", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org.id, user.id, role="owner")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["organization_id"] == org.id
        assert data["roles"] == ["owner"]

    @pytest.mark.asyncio
    async def test_single_membership_valid_header_selects_org(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org = _create_org(db_session, name="Org A")
        await db_session.flush()
        user = _create_user(db_session, display_name="Single Org User", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org.id, user.id, role="member")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}", settings.AUTH_ORGANIZATION_HEADER: org.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["organization_id"] == org.id
        assert data["roles"] == ["member"]

    @pytest.mark.asyncio
    async def test_single_membership_nonexistent_header_returns_403(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org = _create_org(db_session, name="Org A")
        await db_session.flush()
        user = _create_user(db_session, display_name="Single Org User", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org.id, user.id)
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}", settings.AUTH_ORGANIZATION_HEADER: str(uuid.uuid4())},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_multi_membership_foreign_header_returns_403(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org1 = _create_org(db_session, name="Org A")
        await db_session.flush()
        org2 = _create_org(db_session, name="Org B")
        await db_session.flush()
        foreign_org_id = str(uuid.uuid4())
        user = _create_user(db_session, display_name="Multi Org User", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org1.id, user.id, role="owner")
        await db_session.flush()
        _create_membership(db_session, org2.id, user.id, role="viewer")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}", settings.AUTH_ORGANIZATION_HEADER: foreign_org_id},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_multi_membership_inactive_membership_header_returns_403(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org1 = _create_org(db_session, name="Org A")
        await db_session.flush()
        org2 = _create_org(db_session, name="Org B")
        await db_session.flush()
        user = _create_user(db_session, display_name="Multi Org User", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org1.id, user.id, role="owner")
        await db_session.flush()
        _create_membership(db_session, org2.id, user.id, role="viewer", status="inactive")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        # Inactive membership must not satisfy header validation.
        response = oidc_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}", settings.AUTH_ORGANIZATION_HEADER: org2.id},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_principal_roles_from_exact_membership(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org1 = _create_org(db_session, name="Org A")
        await db_session.flush()
        org2 = _create_org(db_session, name="Org B")
        await db_session.flush()
        user = _create_user(db_session, display_name="Multi Role User", external_subject=canonical_key)
        await db_session.flush()
        _create_membership(db_session, org1.id, user.id, role="owner")
        await db_session.flush()
        _create_membership(db_session, org2.id, user.id, role="viewer")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        response = oidc_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}", settings.AUTH_ORGANIZATION_HEADER: org2.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["roles"] == ["viewer"]
        assert data["organization_id"] == org2.id

    @pytest.mark.asyncio
    async def test_no_token_general_returns_401(self, oidc_client):
        response = oidc_client.post("/api/general/run", json={"task": "Hello"})
        assert response.status_code == 401
