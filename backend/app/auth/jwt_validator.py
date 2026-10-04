"""JWT validation for OIDC bearer tokens.

Supports local JWKS file and JWKS URL key sources.
"""
from __future__ import annotations

import json
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import jwt
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError, ImmatureSignatureError

from app.config import settings

logger = logging.getLogger(__name__)


class JWTValidationError(Exception):
    pass


class JWTValidator:
    def __init__(self) -> None:
        self._jwks: Optional[Dict[str, Any]] = None
        self._jwks_loaded_at: float = 0.0
        self._jwk_client: Optional[Any] = None

    @property
    def _allowed_algorithms(self) -> List[str]:
        raw = (settings.OIDC_ALLOWED_ALGORITHMS or "RS256").strip()
        return [a.strip() for a in raw.split(",") if a.strip()]

    def _load_jwks_file(self) -> Dict[str, Any]:
        path = settings.OIDC_JWKS_FILE.strip()
        if not path:
            raise JWTValidationError("OIDC_JWKS_FILE is not configured")
        p = Path(path)
        if not p.is_file():
            raise JWTValidationError(f"OIDC_JWKS_FILE not found: {path}")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise JWTValidationError(f"Invalid JWKS JSON: {exc}") from exc
        if "keys" not in data:
            raise JWTValidationError("JWKS JSON missing 'keys' array")
        return data

    def _get_jwks(self) -> Dict[str, Any]:
        ttl = settings.OIDC_JWKS_CACHE_TTL_SECONDS
        now = time.time()
        if self._jwks is not None and (now - self._jwks_loaded_at) < ttl:
            return self._jwks

        if settings.OIDC_JWKS_FILE.strip():
            self._jwks = self._load_jwks_file()
        elif settings.OIDC_JWKS_URL.strip():
            if self._jwk_client is None:
                self._jwk_client = jwt.PyJWKClient(
                    settings.OIDC_JWKS_URL.strip(),
                    cache_jwk_set=True,
                    cache_jwk_set_ttl=ttl,
                )
            self._jwks = self._jwk_client.get_jwk_set().__dict__
        else:
            raise JWTValidationError("No OIDC_JWKS_FILE or OIDC_JWKS_URL configured")
        self._jwks_loaded_at = now
        return self._jwks

    def _get_signing_key(self, kid: str) -> Any:
        jwks = self._get_jwks()
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
        raise JWTValidationError(f"Unknown JWKS kid: {kid}")

    def validate(self, token: str) -> Dict[str, Any]:
        if not token or not token.strip():
            raise JWTValidationError("Empty token")
        token = token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        header = jwt.get_unverified_header(token)
        payload = jwt.decode(token, options={"verify_signature": False})
        alg = header.get("alg", "")
        if alg == "none" or alg.lower() == "none":
            raise JWTValidationError("Algorithm 'none' is not allowed")
        allowed = self._allowed_algorithms
        if alg not in allowed:
            raise JWTValidationError(f"Algorithm '{alg}' is not allowed (allowed: {allowed})")

        kid = header.get("kid")
        if not kid:
            raise JWTValidationError("Missing 'kid' in token header")

        issuer = settings.OIDC_ISSUER.strip()
        audience = settings.OIDC_AUDIENCE.strip()
        if not issuer or not audience:
            raise JWTValidationError("OIDC_ISSUER and OIDC_AUDIENCE must be configured")

        clock_skew = settings.OIDC_CLOCK_SKEW_SECONDS
        signing_key = self._get_signing_key(kid)

        try:
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=allowed,
                issuer=issuer,
                audience=audience,
                leeway=clock_skew,
            )
        except ExpiredSignatureError as exc:
            raise JWTValidationError("Token expired") from exc
        except ImmatureSignatureError as exc:
            raise JWTValidationError("Token not yet valid (nbf)") from exc
        except InvalidTokenError as exc:
            raise JWTValidationError(f"Invalid token: {exc}") from exc

        sub = payload.get("sub")
        if not sub or not str(sub).strip():
            raise JWTValidationError("Missing 'sub' claim")
        return payload


jwt_validator = JWTValidator()
