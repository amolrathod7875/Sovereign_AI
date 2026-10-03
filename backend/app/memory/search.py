"""M5 semantic memory search service.

Two-stage search:
  1. Qdrant candidate retrieval with coarse filters
  2. PostgreSQL canonical + authorization validation

PostgreSQL remains canonical truth. Qdrant payload is never trusted directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional

from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.config import settings
from app.identity.principal import Principal
from app.memory.index_config import (
    MEMORY_QDRANT_COLLECTION,
    MEMORY_SEARCH_CANDIDATE_MULTIPLIER,
    MEMORY_SEARCH_DEFAULT_TOP_K,
)
from app.memory.repository import MemoryRepository
from app.memory.schemas import MemoryScope
from app.memory.vector_store import MemoryVectorStore
from app.storage.postgres import async_session, Conversation

logger = logging.getLogger(__name__        )


@dataclass
class MemorySearchResult:
    memory_id: str
    content: str
    scope: str
    memory_type: str
    semantic_score: float
    importance: float
    confidence: float
    user_id: str
    conversation_id: Optional[str] = None
    version: int = 1
    updated_at: Optional[str] = None


@dataclass
class MemorySearchResponse:
    query: str
    results: List[MemorySearchResult] = field(default_factory=list)
    index: str = MEMORY_QDRANT_COLLECTION
    retrieval_mode: str = "semantic_memory"
    embedding_local: bool = True
    candidate_count: int = 0
    returned_count: int = 0


class MemorySemanticSearch:
    """Semantic memory search backed by local Qdrant + PostgreSQL canonical validation."""

    def __init__(
        self,
        store: Optional[MemoryVectorStore] = None,
        top_k: int = MEMORY_SEARCH_DEFAULT_TOP_K,
        candidate_multiplier: int = MEMORY_SEARCH_CANDIDATE_MULTIPLIER,
    ) -> None:
        self.store = store or MemoryVectorStore()
        self.top_k = top_k
        self.candidate_multiplier = candidate_multiplier

    async def close(self) -> None:
        self.store.close()

    async def search_memories(
        self,
        principal: Principal,
        query: str,
        conversation_id: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> MemorySearchResponse:
        top_k = top_k or self.top_k
        response = MemorySearchResponse(query=query)

        if conversation_id:
            async with async_session() as session:
                repo = MemoryRepository(session)
                conv = await repo.validate_conversation_access(principal, conversation_id)
            if conv is None:
                logger.warning("Unauthorized conversation_id in memory search: %s", conversation_id)
                response.candidate_count = 0
                response.returned_count = 0
                return response

        if not self.store.collection_exists():
            logger.warning("Memory Qdrant collection %s does not exist", MEMORY_QDRANT_COLLECTION)
            return response

        from rag.models.embeddings import LocalEmbedder, EmbeddingModelUnavailable
        try:
            embedder = LocalEmbedder(settings.EMBEDDING_MODEL)
        except EmbeddingModelUnavailable as exc:
            logger.error("Local embedding model unavailable for memory search: %s", exc)
            return response

        query_vector = embedder.embed([query])[0]
        candidate_top_k = top_k * self.candidate_multiplier

        qdrant_filter = self._build_qdrant_filter(principal, conversation_id)
        hits = self.store.search(query_vector, top_k=candidate_top_k, qdrant_filter=qdrant_filter)
        response.candidate_count = len(hits)

        if not hits:
            return response

        validated = await self._validate_candidates(principal, hits, conversation_id)
        response.results = validated[:top_k]
        response.returned_count = len(response.results)
        return response

    def _build_qdrant_filter(
        self,
        principal: Principal,
        conversation_id: Optional[str],
    ) -> Optional[Filter]:
        """Build coarse Qdrant filter for allowed scopes.

        M5 only allows PERSONAL always, and CONVERSATION only when conversation_id is supplied.
        PROJECT and ORGANIZATION are excluded from automatic search in M5.
        """
        must = [
            FieldCondition(key="organization_id", match=MatchValue(value=principal.organization_id)),
            FieldCondition(key="user_id", match=MatchValue(value=principal.user_id)),
            FieldCondition(key="active", match=MatchValue(value=True)),
        ]
        if conversation_id:
            filter = Filter(
                must=must,
                should=[
                    FieldCondition(key="scope", match=MatchValue(value=MemoryScope.PERSONAL.value)),
                    Filter(
                        must=[
                            FieldCondition(key="scope", match=MatchValue(value=MemoryScope.CONVERSATION.value)),
                            FieldCondition(key="conversation_id", match=MatchValue(value=conversation_id)),
                        ]
                    ),
                ],
            )
            return filter
        must.append(FieldCondition(key="scope", match=MatchValue(value=MemoryScope.PERSONAL.value)))
        return Filter(must=must)

    async def _validate_candidates(
        self,
        principal: Principal,
        hits: List[Dict[str, Any]],
        requested_conversation_id: Optional[str],
    ) -> List[MemorySearchResult]:
        """Revalidate Qdrant candidates against PostgreSQL canonical state.

        Returns only authorized, active, non-expired canonical memories.
        """
        memory_ids = []
        id_to_hit = {}
        for hit in hits:
            pid = hit.get("payload", {}).get("memory_id") or hit.get("point_id")
            if pid:
                memory_ids.append(pid)
                id_to_hit[pid] = hit

        if not memory_ids:
            return []

        async with async_session() as session:
            repo = MemoryRepository(session)
            results: List[MemorySearchResult] = []
            for memory_id in memory_ids:
                hit = id_to_hit[memory_id]
                memory = await repo.get_memory(principal, memory_id)
                if memory is None:
                    continue
                if not memory.active:
                    continue
                if memory.expires_at and memory.expires_at <= _now_utc():
                    continue
                if memory.scope == MemoryScope.CONVERSATION.value:
                    if not requested_conversation_id or memory.conversation_id != requested_conversation_id:
                        continue
                results.append(
                    MemorySearchResult(
                        memory_id=memory.id,
                        content=memory.content,
                        scope=memory.scope,
                        memory_type=memory.memory_type,
                        semantic_score=hit.get("score", 0.0),
                        importance=float(memory.importance),
                        confidence=float(memory.confidence),
                        user_id=memory.user_id,
                        conversation_id=memory.conversation_id,
                        version=int(memory.version),
                        updated_at=memory.updated_at.isoformat() if memory.updated_at else None,
                    )
                )
            return results

    async def index_status(self) -> Dict[str, Any]:
        return {
            "collection_exists": self.store.collection_exists(),
            "collection": MEMORY_QDRANT_COLLECTION,
            "point_count": self.store.point_count(),
        }


def _now_utc() -> datetime:
    return datetime.utcnow()
