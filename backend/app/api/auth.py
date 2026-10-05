"""A1A + A1B authentication API endpoints."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.identity.principal import Principal, get_current_principal_dep
from app.storage.postgres import Organization

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class AuthMeResponse(BaseModel):
    user_id: str
    organization_id: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    roles: list[str] = []
    authenticated: bool = False
    source: str = "local_development"


class AuthConfigResponse(BaseModel):
    auth_mode: str
    authentication_required: bool
    oidc: Optional[dict] = None


class AuthBootstrapMembership(BaseModel):
    organization_id: str
    organization_name: str
    role: str


class AuthBootstrapUser(BaseModel):
    user_id: str
    display_name: str
    email: Optional[str] = None


class AuthBootstrapResponse(BaseModel):
    user: AuthBootstrapUser
    memberships: list[AuthBootstrapMembership] = []


# ---------------------------------------------------------------------------
# /api/auth/me
# ---------------------------------------------------------------------------


@router.get("/me", response_model=AuthMeResponse)
async def auth_me(
    principal: Principal = Depends(get_current_principal_dep),
):
    return AuthMeResponse(
        user_id=principal.user_id,
        organization_id=principal.organization_id,
        display_name=None,
        email=None,
        roles=principal.roles,
        authenticated=principal.authenticated,
        source=principal.source,
    )


# ---------------------------------------------------------------------------
# /api/auth/config  (PUBLIC — no token required)
# ---------------------------------------------------------------------------


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config():
    mode = (settings.AUTH_MODE or "development").strip().lower()

    if mode == "development":
        return AuthConfigResponse(
            auth_mode="development",
            authentication_required=False,
            oidc=None,
        )

    if mode != "oidc":
        return AuthConfigResponse(
            auth_mode=mode,
            authentication_required=False,
            oidc=None,
        )

    client_id = settings.OIDC_CLIENT_ID.strip()
    authority = settings.OIDC_ISSUER.strip()
    scope = settings.OIDC_FRONTEND_SCOPES.strip()

    if not client_id or not authority:
        return AuthConfigResponse(
            auth_mode="oidc",
            authentication_required=False,
            oidc=None,
        )

    return AuthConfigResponse(
        auth_mode="oidc",
        authentication_required=True,
        oidc={
            "authority": authority,
            "client_id": client_id,
            "scope": scope or "openid profile email",
        },
    )


# ---------------------------------------------------------------------------
# /api/auth/bootstrap  (TOKEN_ONLY — valid JWT required, no org header)
# ---------------------------------------------------------------------------


def _get_token_only_identity(request: Request) -> dict:
    identity = getattr(request.state, "authenticated_identity", None)
    if identity is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return identity


@router.get("/bootstrap", response_model=AuthBootstrapResponse)
async def auth_bootstrap(request: Request):
    identity = _get_token_only_identity(request)
    user_id = identity["user_id"]
    display_name = identity.get("display_name", "")
    email = identity.get("email")

    from app.storage.postgres import async_session, OrganizationMembership
    from sqlalchemy import select as sa_select

    session = async_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        memberships_stmt = (
            sa_select(OrganizationMembership, Organization)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == "active",
            )
        )
        result = await session.execute(memberships_stmt)
        rows = result.all()
    finally:
        await session.close()

    if not rows:
        raise HTTPException(status_code=403, detail="No active organization memberships")

    memberships = []
    for membership, org in rows:
        memberships.append(
            AuthBootstrapMembership(
                organization_id=membership.organization_id,
                organization_name=org.name,
                role=membership.role,
            )
        )

    return AuthBootstrapResponse(
        user=AuthBootstrapUser(
            user_id=user_id,
            display_name=display_name,
            email=email,
        ),
        memberships=memberships,
    )
