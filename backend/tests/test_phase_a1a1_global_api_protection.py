"""Phase A1A.1 — Global OIDC API protection tests.

Verifies that in AUTH_MODE=oidc every sensitive /api route is authenticated
by default, with only a minimal public allowlist exempt.
"""
from __future__ import annotations

import sys
import json
import time
import uuid
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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
# Route enumeration
# ---------------------------------------------------------------------------


def _get_api_routes() -> list[tuple[str, str, str]]:
    routes = []
    for route in _fastapi_app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            path = route.path
            if path.startswith("/api"):
                tag = route.tags[0] if getattr(route, "tags", []) else ""
                for method in route.methods:
                    if method in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
                        routes.append((method, path, tag))
    routes.sort()
    return routes


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRouteEnumeration:
    def test_api_routes_discovered(self):
        routes = _get_api_routes()
        assert len(routes) > 0, "expected registered /api routes"

    def test_public_paths_exist(self):
        actual_paths = {path for _, path, _ in _get_api_routes()}
        assert "/api/system/health" in actual_paths


class TestDevelopmentMode:
    async def test_root_accessible(self, development_client):
        response = development_client.get("/")
        assert response.status_code == 200

    async def test_health_accessible(self, development_client):
        response = development_client.get("/api/system/health")
        assert response.status_code == 200

    async def test_general_accessible_without_token(self, development_client):
        response = development_client.post("/api/general/run", json={"task": "ping"})
        assert response.status_code != 401

    async def test_auth_me_returns_dev_principal(self, development_client):
        response = development_client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["source"] == "local_development"

    async def test_options_bypasses_auth(self, development_client):
        response = development_client.options("/api/general/run", headers={})
        assert response.status_code in (200, 204, 405)


class TestOIDCModePublicRoutes:
    async def test_root_public(self, oidc_client):
        response = oidc_client.get("/")
        assert response.status_code == 200

    async def test_health_public(self, oidc_client):
        response = oidc_client.get("/api/system/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    async def test_options_bypasses_auth(self, oidc_client):
        response = oidc_client.options("/api/general/run", headers={})
        assert response.status_code in (200, 204, 405)

    async def test_docs_allowed(self, oidc_client):
        response = oidc_client.get("/docs")
        assert response.status_code in (200, 307)

    async def test_openapi_json_allowed(self, oidc_client):
        response = oidc_client.get("/openapi.json")
        assert response.status_code == 200


class TestOIDCModeProtectedRoutes:
    async def test_missing_token_returns_401(self, oidc_client):
        response = oidc_client.get("/api/auth/me")
        assert response.status_code == 401
        assert "bearer" in response.headers.get("www-authenticate", "").lower()

    async def test_general_no_token_401(self, oidc_client):
        response = oidc_client.post("/api/general/run", json={"task": "ping"})
        assert response.status_code == 401

    async def test_conversations_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/conversations")
        assert response.status_code == 401

    async def test_memory_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/memory/memory")
        assert response.status_code == 401

    async def test_documents_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/documents")
        assert response.status_code == 401

    async def test_rag_no_token_401(self, oidc_client):
        response = oidc_client.post("/api/rag/search", json={"query": "test"})
        assert response.status_code == 401

    async def test_models_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/models")
        assert response.status_code == 401

    async def test_sandbox_no_token_401(self, oidc_client):
        response = oidc_client.post("/api/sandbox/execute", json={"code": "print(1)"})
        assert response.status_code == 401

    async def test_executions_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/executions")
        assert response.status_code == 401

    async def test_network_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/network/monitor")
        assert response.status_code == 401

    async def test_agent_no_token_401(self, oidc_client):
        response = oidc_client.post("/api/agent/run", json={"task": "ping"})
        assert response.status_code == 401

    async def test_coder_no_token_401(self, oidc_client):
        response = oidc_client.post("/api/coder/run", json={"task": "echo hello"})
        assert response.status_code == 401

    async def test_vision_no_token_401(self, oidc_client):
        response = oidc_client.post("/api/vision/analyze", json={})
        assert response.status_code == 401

    async def test_artifacts_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/artifacts")
        assert response.status_code == 401

    async def test_artifact_download_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/artifacts/fake-id/download")
        assert response.status_code == 401

    async def test_approvals_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/approvals/pending")
        assert response.status_code == 401

    async def test_receipts_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/receipts/nonexistent")
        assert response.status_code == 401

    async def test_receipt_chain_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/receipt-chain")
        assert response.status_code == 401

    async def test_judge_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/judge/overview")
        assert response.status_code == 401

    async def test_chat_no_token_401(self, oidc_client):
        response = oidc_client.post("/api/chat", json={"message": "hi"})
        assert response.status_code == 401

    async def test_system_status_no_token_401(self, oidc_client):
        response = oidc_client.get("/api/system/status")
        assert response.status_code == 401


class TestOIDCModeValidToken:
    async def test_auth_me_with_token(
        self, oidc_client, db_session, rsa_keypair, unique_subject
    ):
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

    async def test_valid_token_passes_other_protected_routes(
        self, oidc_client, db_session, rsa_keypair, unique_subject
    ):
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
        headers = {"Authorization": f"Bearer {token}"}

        response = oidc_client.get("/api/system/status", headers=headers)
        assert response.status_code != 401

        response = oidc_client.get("/api/conversations", headers=headers)
        assert response.status_code != 401

        response = oidc_client.get("/api/memory/memory", headers=headers)
        assert response.status_code != 401

    async def test_organization_selection_preserved(
        self, oidc_client, db_session, rsa_keypair, unique_subject
    ):
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
        _create_membership(db_session, org2.id, user.id, role="viewer")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")

        response = oidc_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}", settings.AUTH_ORGANIZATION_HEADER: org2.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["organization_id"] == org2.id
        assert data["roles"] == ["viewer"]


class TestOIDCModeSideEffects:
    async def test_no_token_blocks_general_model(
        self, oidc_client, monkeypatch
    ):
        call_count = 0

        async def fake_synth(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"used": False, "reason": "no model"}

        from app.api import general as general_mod
        monkeypatch.setattr(general_mod, "_try_general_synthesis", fake_synth)

        response = oidc_client.post("/api/general/run", json={"task": "ping"})
        assert response.status_code == 401
        assert call_count == 0

    async def test_no_token_blocks_artifact_download(
        self, oidc_client
    ):
        response = oidc_client.get("/api/artifacts/fake-id/download")
        assert response.status_code == 401
        assert b"Missing bearer token" in response.content


class TestOIDCModeJWTValidation:
    async def test_alg_none_rejected(self, oidc_client, unique_subject):
        payload = {
            "sub": unique_subject,
            "iss": settings.OIDC_ISSUER,
            "aud": settings.OIDC_AUDIENCE,
            "exp": int(time.time() + 3600),
        }
        token = pyjwt.encode(payload, "", algorithm="none")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    async def test_expired_token_401(self, oidc_client, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        token = _sign_token(private_key, unique_subject, settings.OIDC_ISSUER, settings.OIDC_AUDIENCE, "test-key-1", expiry_seconds=-120)
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    async def test_future_nbf_401(self, oidc_client, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        from datetime import datetime, timedelta, timezone
        nbf = datetime.now(timezone.utc) + timedelta(minutes=5)
        token = _sign_token(private_key, unique_subject, settings.OIDC_ISSUER, settings.OIDC_AUDIENCE, "test-key-1", not_before=nbf)
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


class TestOIDCModeIdentityResolution:
    async def test_unknown_user_403(self, oidc_client, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        subject = f"unknown-{unique_subject}"
        token = _sign_token(private_key, subject, settings.OIDC_ISSUER, settings.OIDC_AUDIENCE, "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    async def test_inactive_user_403(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        subject = f"inactive-{unique_subject}"
        canonical_key = f"{settings.OIDC_ISSUER}|{subject}"

        org = _create_org(db_session, name="Test Org")
        await db_session.flush()
        user = _create_user(db_session, display_name="Inactive User", external_subject=canonical_key, active=False)
        await db_session.flush()
        _create_membership(db_session, org.id, user.id)
        await db_session.commit()

        token = _sign_token(private_key, subject, settings.OIDC_ISSUER, settings.OIDC_AUDIENCE, "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    async def test_no_membership_403(self, oidc_client, db_session, rsa_keypair, unique_subject):
        private_key, _ = rsa_keypair
        subject = f"no-membership-{unique_subject}"
        canonical_key = f"{settings.OIDC_ISSUER}|{subject}"

        user = _create_user(db_session, display_name="No Membership", external_subject=canonical_key)
        await db_session.commit()

        token = _sign_token(private_key, subject, settings.OIDC_ISSUER, settings.OIDC_AUDIENCE, "test-key-1")
        response = oidc_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    async def test_single_membership_auto_selects(
        self, oidc_client, db_session, rsa_keypair, unique_subject
    ):
        private_key, _ = rsa_keypair
        issuer = settings.OIDC_ISSUER
        audience = settings.OIDC_AUDIENCE
        subject = unique_subject
        canonical_key = f"{issuer}|{subject}"

        org = _create_org(db_session, name="Test Org")
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

    async def test_foreign_org_header_403(
        self, oidc_client, db_session, rsa_keypair, unique_subject
    ):
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
        _create_membership(db_session, org2.id, user.id, role="viewer")
        await db_session.commit()

        token = _sign_token(private_key, subject, issuer, audience, "test-key-1")
        foreign_org_id = str(uuid.uuid4())
        response = oidc_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}", settings.AUTH_ORGANIZATION_HEADER: foreign_org_id},
        )
        assert response.status_code == 403

    async def test_roles_from_selected_membership(
        self, oidc_client, db_session, rsa_keypair, unique_subject
    ):
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


class TestOIDCModeWWWAuthenticate:
    async def test_401_includes_bearer_challenge(self, oidc_client):
        response = oidc_client.get("/api/auth/me")
        assert response.status_code == 401
        www_auth = response.headers.get("www-authenticate", "")
        assert "bearer" in www_auth.lower()
