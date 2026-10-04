"""Authentication dataclass and dependency for Sovereign AI.

M1 local development principal abstraction. Future Phase A authentication will
replace ONLY the resolver that produces this object. All history APIs obtain
identity through get_current_principal() or an equivalent dependency — never
from hard-coded user IDs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

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


async def get_current_principal_dep(request: Request) -> Principal:
    """FastAPI dependency that returns the current principal.

    In OIDC mode the global AuthenticationMiddleware has already validated the
    JWT and stored the resolved Principal on request.state.principal.  We reuse
    that object here so the token is not validated twice.

    In development mode we return the deterministic dev principal.
    """
    mode = (settings.AUTH_MODE or "development").strip().lower()

    if mode == "oidc":
        principal = getattr(request.state, "principal", None)
        if principal is not None:
            return principal
        raise HTTPException(status_code=401, detail="Missing bearer token")

    return get_dev_principal()
