"""OIDC authentication dependency for FastAPI.

Provides request-scoped principal resolution:
  1. In AUTH_MODE=development: returns the deterministic dev principal.
  2. In AUTH_MODE=oidc: validates the Authorization: Bearer JWT and resolves
     the authenticated principal from PostgreSQL.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_validator import JWTValidationError, jwt_validator
from app.auth.resolver import PrincipalResolutionError, PrincipalResolver
from app.config import settings
from app.identity.principal import Principal, get_dev_principal
from app.storage.postgres import async_session

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
) -> Principal:
    """Return the current request principal.

    In dev mode, returns the deterministic dev principal.
    In OIDC mode, validates the bearer token and resolves the principal from DB.
    """
    mode = (settings.AUTH_MODE or "development").strip().lower()

    if mode == "development":
        return get_dev_principal()

    if mode != "oidc":
        raise HTTPException(status_code=500, detail=f"Unknown AUTH_MODE: {mode}")

    if credentials is None or not credentials.credentials.strip():
        raise HTTPException(
            status_code=401,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()
    try:
        payload = jwt_validator.validate(token)
    except JWTValidationError as exc:
        logger.warning("JWT validation failed: %s", exc)
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

    session: AsyncSession = async_session()
    if session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    resolver = PrincipalResolver(session, issuer, subject)
    if requested_org_id:
        resolver.requested_org_id = requested_org_id

    try:
        principal = await resolver.resolve()
    except PrincipalResolutionError as exc:
        logger.warning("Principal resolution failed: %s", exc)
        raise HTTPException(status_code=403, detail=str(exc))
    finally:
        await session.close()

    return principal
