"""OIDC authentication boundary for Sovereign AI.

Provides:
1. Global authentication middleware that enforces OIDC auth on sensitive routes.
2. FastAPI dependency that reuses the principal resolved by the middleware.

Path classifications:
  PUBLIC        no token required
  TOKEN_ONLY    valid JWT required, issuer/sub validated, user mapped checked,
                memberships available — organization NOT selected yet
  FULL_PRINCIPAL valid JWT + active mapped user + selected organization membership
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth.jwt_validator import JWTValidationError, jwt_validator
from app.auth.resolver import PrincipalResolutionError, PrincipalResolver
from app.config import settings
from app.identity.principal import Principal, get_dev_principal
from app.storage.postgres import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public / token-only allowlists
# ---------------------------------------------------------------------------

_PUBLIC_PATHS: set[str] = {
    "/",
    "/api/system/health",
    "/api/auth/config",
}

_TOKEN_ONLY_PATHS: set[str] = {
    "/api/auth/bootstrap",
}


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_PATHS


def _is_token_only_path(path: str) -> bool:
    return path in _TOKEN_ONLY_PATHS


# ---------------------------------------------------------------------------
# Global middleware
# ---------------------------------------------------------------------------


class AuthenticationMiddleware:
    """Global OIDC authentication boundary.

    In AUTH_MODE=development every request passes through untouched.

    In AUTH_MODE=oidc:
      * OPTIONS requests bypass auth (CORS preflight).
      * PUBLIC paths bypass auth.
      * TOKEN_ONLY paths require a valid Bearer JWT and mapped active user,
        but do NOT require organization selection.
      * FULL_PRINCIPAL paths (default for /api) require valid JWT + org selection.
      * Non-/api paths (docs, static files) are allowed through.
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
            from fastapi.responses import JSONResponse
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

        # Token-only paths: validate JWT + mapped user, no org required.
        if _is_token_only_path(path):
            if not await self._require_token_only(request, scope, receive, send):
                return
            await self.app(scope, receive, send)
            return

        # Non-API paths (static files, docs, etc.) are allowed through.
        if not path.startswith("/api"):
            await self.app(scope, receive, send)
            return

        # Default: full principal required (JWT + org selection).
        if not await self._require_full_principal(request, scope, receive, send):
            return
        await self.app(scope, receive, send)

    async def _require_token_only(self, request: Request, scope, receive, send) -> bool:
        """Validate Bearer JWT and mapped active user; store minimal identity.

        Does NOT require organization selection.
        Returns True if the request should continue to the app.
        """
        auth = request.headers.get("authorization", "").strip()
        if not auth or not auth.lower().startswith("bearer "):
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "Missing bearer token"},
            )
            await response(scope, receive, send)
            return False

        token = auth[7:].strip()
        if not token:
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "Missing bearer token"},
            )
            await response(scope, receive, send)
            return False

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
            return False

        issuer = payload.get("iss", "")
        subject = payload.get("sub", "")
        if not issuer or not subject:
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "Token missing required claims"},
            )
            await response(scope, receive, send)
            return False

        canonical_key = f"{issuer}|{subject}"

        from app.storage.postgres import async_session
        session: AsyncSession = async_session()
        if session is None:
            response = JSONResponse(
                status_code=503,
                content={"detail": "Database unavailable"},
            )
            await response(scope, receive, send)
            return False

        try:
            stmt = select(User).where(User.external_subject == canonical_key, User.active.is_(True))
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
        finally:
            await session.close()

        if user is None:
            response = JSONResponse(
                status_code=403,
                content={"detail": "Unknown or inactive user"},
            )
            await response(scope, receive, send)
            return False

        request.state.authenticated_identity = {
            "issuer": issuer,
            "subject": subject,
            "user_id": user.id,
            "display_name": user.display_name,
            "email": user.email,
        }
        return True

    async def _require_full_principal(self, request: Request, scope, receive, send) -> bool:
        """Validate Bearer JWT and resolve full Principal including organization.

        Returns True if the request should continue to the app.
        """
        auth = request.headers.get("authorization", "").strip()
        if not auth or not auth.lower().startswith("bearer "):
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "Missing bearer token"},
            )
            await response(scope, receive, send)
            return False

        token = auth[7:].strip()
        if not token:
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "Missing bearer token"},
            )
            await response(scope, receive, send)
            return False

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
            return False

        issuer = payload.get("iss", "")
        subject = payload.get("sub", "")
        if not issuer or not subject:
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "Token missing required claims"},
            )
            await response(scope, receive, send)
            return False

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
            return False

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
            return False
        finally:
            await session.close()

        request.state.principal = principal
        return True


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
