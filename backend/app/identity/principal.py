"""Authentication dataclass and dependency for Sovereign AI.

M1 local development principal abstraction. Future Phase A authentication will
replace ONLY the resolver that produces this object. All history APIs obtain
identity through get_current_principal() or an equivalent dependency — never
from hard-coded user IDs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from fastapi import HTTPException, Request

from app.config import settings


@dataclass
class Principal:
    """Authenticated principal."""

    user_id: str
    organization_id: str
    roles: List[str] = field(default_factory=list)
    authenticated: bool = False
    source: str = "local_development"


def get_dev_principal() -> Principal:
    """Return the deterministic development principal."""
    return Principal(
        user_id=settings.SOVEREIGN_DEV_USER_ID,
        organization_id=settings.SOVEREIGN_DEV_ORGANIZATION_ID,
        roles=["owner"],
        authenticated=False,
        source="local_development",
    )


def get_current_principal() -> Principal:
    """Return the current principal.

    M1 local development: returns a deterministic dev principal sourced from
    app.config.settings. Real authentication is NOT implemented yet.
    """
    return get_dev_principal()


async def get_oidc_principal(request: Request) -> Principal:
    """Validate OIDC bearer token and return authenticated principal."""
    auth = request.headers.get("authorization", "").strip()
    if not auth:
        raise HTTPException(
            status_code=401,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from app.auth.jwt_validator import JWTValidationError, jwt_validator
    from app.auth.resolver import PrincipalResolutionError, PrincipalResolver
    from app.storage.postgres import async_session

    try:
        payload = jwt_validator.validate(auth)
    except JWTValidationError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    issuer = payload.get("iss", "")
    subject = payload.get("sub", "")
    if not issuer or not subject:
        raise HTTPException(
            status_code=401,
            detail="Token missing required claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    org_header = settings.AUTH_ORGANIZATION_HEADER.strip()
    requested_org_id = request.headers.get(org_header, "").strip() or None

    session = async_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resolver = PrincipalResolver(session, issuer, subject)
    if requested_org_id:
        resolver.requested_org_id = requested_org_id

    try:
        principal = await resolver.resolve()
    except PrincipalResolutionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    finally:
        await session.close()

    return principal


async def get_current_principal_dep(request: Request) -> Principal:
    """FastAPI dependency that dispatches to the correct auth resolver."""
    mode = (settings.AUTH_MODE or "development").strip().lower()
    if mode == "oidc":
        return await get_oidc_principal(request)
    return get_current_principal()
