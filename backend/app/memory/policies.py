"""Conservative memory extraction policies for M4.

These thresholds and rules enforce that only durable, explicit, non-sensitive
statements become canonical long-term memory. Memory extraction is secondary
to the primary user response and must fail closed (skip memory) when uncertain.
"""
from __future__ import annotations

from app.memory.schemas import MemoryScope, MemoryType


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

MEMORY_MIN_IMPORTANCE: float = 0.60
MEMORY_MIN_CONFIDENCE: float = 0.75
MEMORY_MAX_CANDIDATES_PER_TURN: int = 3
MEMORY_CONTENT_MAX_LENGTH: int = 1000


# ---------------------------------------------------------------------------
# Scopes allowed for automatic extraction
# ---------------------------------------------------------------------------

AUTOMATIC_SCOPES = {MemoryScope.PERSONAL, MemoryScope.CONVERSATION}

RESERVED_SCOPES = {MemoryScope.PROJECT, MemoryScope.ORGANIZATION}


# ---------------------------------------------------------------------------
# Secret / sensitive content rejection patterns
# ---------------------------------------------------------------------------

SECRET_PATTERNS = [
    "password",
    "api_key",
    "api_secret",
    "secret key",
    "private key",
    "begin private key",
    "token",
    "credential",
    "access token",
    "auth_token",
    "database url",
    "database_password",
    "db_password",
]


def is_secret_like(text: str) -> bool:
    """Return True if the candidate text looks like it contains a secret.

    This is intentionally conservative: it only catches obvious cases.
    It is NOT a substitute for proper secret scanning.
    """
    lower = text.lower()
    return any(pattern in lower for pattern in SECRET_PATTERNS)


# ---------------------------------------------------------------------------
# Low-value utterance rejection patterns
# ---------------------------------------------------------------------------

TRANSIENT_PATTERNS = [
    "okay",
    "thanks",
    "thank you",
    "continue",
    "try again",
    "yes",
    "no",
    "good",
    "regenerate",
    "explain ",
    "what is",
    "what are",
    "tell me about",
    "run this",
    "please continue",
]


def is_transient_utterance(text: str) -> bool:
    """Return True if the candidate text looks like a transient chat utterance.

    These are statements that should NOT become durable memory because they
    are meta-requests, greetings, or temporary feedback rather than durable facts.
    """
    import re
    stripped = re.sub(r"[.!?]+$", "", text.strip()).lower()
    if len(stripped) <= 3:
        return True
    for pattern in TRANSIENT_PATTERNS:
        if stripped == pattern or stripped.startswith(pattern + " "):
            return True
    return False
