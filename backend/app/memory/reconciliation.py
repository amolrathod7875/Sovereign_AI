"""M5 memory index reconciliation: compare PostgreSQL canonical state to Qdrant.

Repair direction is always POSTGRES_TO_QDRANT. Qdrant is derived state only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.memory.index_config import MEMORY_QDRANT_COLLECTION
from app.memory.repository import MemoryRepository
from app.memory.vector_store import MemoryVectorStore
from app.storage.postgres import ConversationMemory, async_session

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationDelta:
    missing: List[str] = field(default_factory=list)
    orphan: List[str] = field(default_factory=list)
    stale_version: List[str] = field(default_factory=list)
    inactive_present: List[str] = field(default_factory=list)
    expired_present: List[str] = field(default_factory=list)


class MemoryReconciliation:
    """Detect and repair drift between PostgreSQL canonical memories and Qdrant."""

    def __init__(self, store: Optional[MemoryVectorStore] = None) -> None:
        self.store = store or MemoryVectorStore()

    async def close(self) -> None:
        self.store.close()

    async def diff(self) -> ReconciliationDelta:
        delta = ReconciliationDelta()
        if not self.store.collection_exists():
            return delta

        qdrant_ids = set()
        try:
            scroll = self.store.client.scroll(
                collection_name=MEMORY_QDRANT_COLLECTION,
                limit=4096,
                with_payload=True,
            )
            for point in scroll[0]:
                pid = point.payload.get("memory_id") or point.id
                if pid:
                    qdrant_ids.add(str(pid))
        except Exception as exc:
            logger.error("Failed to scan Qdrant collection: %s", exc)
            return delta

        async with async_session() as session:
            repo = MemoryRepository(session)
            stmt = select(ConversationMemory).where(ConversationMemory.id.in_(list(qdrant_ids)))
            result = await session.execute(stmt)
            memories = {m.id: m for m in result.scalars().all()}

            for memory_id in qdrant_ids:
                memory = memories.get(memory_id)
                if memory is None:
                    delta.orphan.append(memory_id)
                    continue
                payload_version = None
                try:
                    scroll = self.store.client.scroll(
                        collection_name=MEMORY_QDRANT_COLLECTION,
                        limit=1,
                        with_payload=True,
                        scroll_filter=None,
                    )
                    for point in scroll[0]:
                        pid = point.payload.get("memory_id") or point.id
                        if str(pid) == memory_id:
                            payload_version = point.payload.get("version")
                            break
                except Exception:
                    pass
                if payload_version is not None and int(payload_version) != memory.version:
                    delta.stale_version.append(memory_id)
                if not memory.active:
                    delta.inactive_present.append(memory_id)
                elif memory.expires_at and memory.expires_at <= _now_utc():
                    delta.expired_present.append(memory_id)

            active_ids = set()
            stmt2 = (
                select(ConversationMemory.id)
                .where(ConversationMemory.active == True)
                .where(
                    or_(
                        ConversationMemory.expires_at.is_(None),
                        ConversationMemory.expires_at > _now_utc(),
                    )
                )
            )
            result2 = await session.execute(stmt2)
            for row in result2.scalars().all():
                active_ids.add(row)

            for memory_id in active_ids - qdrant_ids:
                delta.missing.append(memory_id)

        return delta

    async def repair(self, delta: ReconciliationDelta) -> Dict[str, int]:
        summary = {"upserted": 0, "deleted": 0, "errors": 0}
        async with async_session() as session:
            repo = MemoryRepository(session)
            try:
                for memory_id in delta.missing:
                    await self._repair_upsert(session, repo, memory_id, summary)
                for memory_id in delta.orphan:
                    try:
                        self.store.delete_point(memory_id)
                        summary["deleted"] += 1
                    except Exception as exc:
                        logger.warning("Failed to delete orphan point %s: %s", memory_id, exc)
                        summary["errors"] += 1
                for memory_id in delta.stale_version:
                    await self._repair_upsert(session, repo, memory_id, summary)
                for memory_id in delta.inactive_present + delta.expired_present:
                    try:
                        self.store.delete_point(memory_id)
                        summary["deleted"] += 1
                    except Exception as exc:
                        logger.warning("Failed to delete stale point %s: %s", memory_id, exc)
                        summary["errors"] += 1
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.error("Reconciliation repair failed: %s", exc)
        return summary

    async def _repair_upsert(self, session: AsyncSession, repo: MemoryRepository, memory_id: str, summary: Dict[str, int]) -> None:
        stmt = select(ConversationMemory).where(ConversationMemory.id == memory_id)
        result = await session.execute(stmt)
        memory = result.scalar_one_or_none()
        if memory is None or not _is_indexable(memory):
            return
        from rag.models.embeddings import LocalEmbedder, EmbeddingModelUnavailable
        try:
            embedder = LocalEmbedder(settings.EMBEDDING_MODEL)
        except EmbeddingModelUnavailable as exc:
            logger.error("Embedding model unavailable for reconciliation upsert %s: %s", memory_id, exc)
            summary["errors"] += 1
            return
        vector = embedder.embed([memory.content or ""])[0]
        payload = {
            "memory_id": memory.id,
            "organization_id": memory.organization_id,
            "user_id": memory.user_id,
            "conversation_id": memory.conversation_id,
            "scope": memory.scope,
            "memory_type": memory.memory_type,
            "content": memory.content,
            "importance": float(memory.importance),
            "confidence": float(memory.confidence),
            "active": bool(memory.active),
            "version": int(memory.version),
            "expires_at": memory.expires_at.isoformat() if memory.expires_at else None,
            "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
        }
        self.store.upsert_point(memory.id, vector, payload)
        summary["upserted"] += 1


def _is_indexable(memory: ConversationMemory) -> bool:
    if not memory.active or not memory.content or not memory.content.strip():
        return False
    if memory.expires_at and memory.expires_at <= _now_utc():
        return False
    return True


def _now_utc() -> datetime:
    return datetime.utcnow()
