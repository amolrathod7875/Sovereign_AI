"""M5 semantic memory index configuration.

Centralizes configuration values for the local embedded Qdrant semantic index.
PostgreSQL remains the canonical memory store; Qdrant is a derived search index only.
"""
from __future__ import annotations

from app.config import settings


MEMORY_QDRANT_PATH = settings.MEMORY_QDRANT_PATH
MEMORY_QDRANT_COLLECTION = settings.MEMORY_QDRANT_COLLECTION
MEMORY_EMBEDDING_DIM = settings.MEMORY_EMBEDDING_DIM
MEMORY_SEARCH_DEFAULT_TOP_K = settings.MEMORY_SEARCH_DEFAULT_TOP_K
MEMORY_SEARCH_CANDIDATE_MULTIPLIER = settings.MEMORY_SEARCH_CANDIDATE_MULTIPLIER
MEMORY_OUTBOX_BATCH_SIZE = settings.MEMORY_OUTBOX_BATCH_SIZE
MEMORY_OUTBOX_MAX_ATTEMPTS = settings.MEMORY_OUTBOX_MAX_ATTEMPTS
MEMORY_OUTBOX_PROCESSING_TIMEOUT_SECONDS = settings.MEMORY_OUTBOX_PROCESSING_TIMEOUT_SECONDS
