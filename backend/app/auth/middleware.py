"""OIDC authentication boundary for Sovereign AI.

Provides:
1. Global authentication middleware that enforces OIDC auth on sensitive routes.
2. FastAPI dependency that reuses the principal resolved by the middleware.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_validator import JWTValidationError, jwt_validator
from app.auth.resolver import PrincipalResolutionError, PrincipalResolver
from app.config import settings
from app.identity.principal import Principal, get_dev_principal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public allowlist (minimal)
# ---------------------------------------------------------------------------

_PUBLIC_PATHS: set[str] = {
    "/",
    "/api/system/health",
}


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_PATHS


# ---------------------------------------------------------------------------
# Global middleware
# ---------------------------------------------------------------------------


class AuthenticationMiddleware:
    """Global OIDC authentication boundary.

    In AUTH_MODE=development every request passes through untouched.

    In AUTH_MODE=oidc:
      * OPTIONS requests bypass auth (CORS preflight).
      * Requests to the minimal public allowlist bypass auth.
      * Non-/api paths (docs, static files) are allowed through.
      * Every other /api request must carry a valid Authorization: Bearer JWT.
      * On success the resolved Principal is stored on request.state.principal.
      * On failure a 401/403 JSON response is returned immediately.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        mode = (settings.AUTH_MODE or "development").strip().lower()

        # Development mode: never require auth.
        if mode == "development":
            await self.app(scope, receive, send)
            return

        # Unknown mode: hard fail rather than silently allowing traffic.
        if mode != "oidc":
            response = JSONResponse(
                status_code=500,
                content={"detail": f"Unknown AUTH_MODE: {mode}"},
            )
            await response(scope, receive, send)
            return

        path = request.url.path

        # CORS preflight must not require a bearer token.
        if request.method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Minimal public allowlist.
        if _is_public_path(path):
            await self.app(scope, receive, send)
            return

        # Non-API paths (static files, docs, etc.) are allowed through.
        if not path.startswith("/api"):
            await self.app(scope, receive, send)
            return

        # Extract bearer token.
        auth = request.headers.get("authorization", "").strip()
        if not auth or not auth.lower().startswith("bearer "):
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "Missing bearer token"},
            )
            await response(scope, receive, send)
            return

        token = auth[7:].strip()
        if not token:
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "Missing bearer token"},
            )
            await response(scope, receive, send)
            return

        # Validate JWT.
        try:
            payload = jwt_validator.validate(token)
        except Exception as exc:
            logger.warning("JWT validation failed: %s", exc)
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": f"Invalid token: {exc}"},
            )
            await response(scope, receive, send)
            return

        issuer = payload.get("iss", "")
        subject = payload.get("sub", "")
        if not issuer or not subject:
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "Token missing required claims"},
            )
            await response(scope, receive, send)
            return

        # Resolve principal from PostgreSQL.
        org_header = settings.AUTH_ORGANIZATION_HEADER.strip()
        requested_org_id = request.headers.get(org_header, "").strip() or None

        from app.storage.postgres import async_session
        session: AsyncSession = async_session()
        if session is None:
            response = JSONResponse(
                status_code=503,
                content={"detail": "Database unavailable"},
            )
            await response(scope, receive, send)
            return

        resolver = PrincipalResolver(session, issuer, subject)
        if requested_org_id:
            resolver.requested_org_id = requested_org_id

        try:
            principal = await resolver.resolve()
        except PrincipalResolutionError as exc:
            logger.warning("Principal resolution failed: %s", exc)
            response = JSONResponse(
                status_code=403,
                content={"detail": str(exc)},
            )
            await response(scope, receive, send)
            return
        finally:
            await session.close()

        # Attach principal to request state for downstream dependencies.
        request.state.principal = principal

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Imports delayed to avoid circular imports at module load time.
# ---------------------------------------------------------------------------

from fastapi.responses import JSONResponse  # noqa: E402
