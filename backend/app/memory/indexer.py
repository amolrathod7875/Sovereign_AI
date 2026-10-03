"""M5 outbox processor: reconcile PostgreSQL canonical memory to Qdrant semantic index.

Architecture:
  PostgreSQL conversation_memories
        │ canonical truth
        ▼
  memory_index_outbox
        │
        ▼
  OutboxProcessor
        │
        ├── load canonical memory
        ├── verify active / expiry / ownership
        ├── embed active memory locally
        ▼
  Qdrant sovereign_memory

Worker MUST reconcile every event against CURRENT canonical PostgreSQL state,
never blindly obey the event.operation. This makes replay safe and prevents
resurrecting inactive memories from stale UPSERT events.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.memory.index_config import (
    MEMORY_OUTBOX_BATCH_SIZE,
    MEMORY_OUTBOX_MAX_ATTEMPTS,
    MEMORY_OUTBOX_PROCESSING_TIMEOUT_SECONDS,
)
from app.memory.schemas import MemoryOutboxOperation, MemoryOutboxStatus
from app.memory.vector_store import MemoryVectorStore
from app.storage.postgres import (
    ConversationMemory,
    MemoryIndexOutbox,
    async_session,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.utcnow()


def _is_expired(memory: Optional[ConversationMemory]) -> bool:
    if memory is None:
        return False
    if memory.expires_at is None:
        return False
    return memory.expires_at <= _now()


def _is_indexable(memory: ConversationMemory) -> bool:
    """Active, non-expired, non-empty content -> should be present in Qdrant."""
    return bool(memory.active and memory.content and memory.content.strip() and not _is_expired(memory))


# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------

class OutboxProcessor:
    """Processes memory_index_outbox events into the local Qdrant semantic index."""

    def __init__(
        self,
        store: Optional[MemoryVectorStore] = None,
        batch_size: int = MEMORY_OUTBOX_BATCH_SIZE,
        max_attempts: int = MEMORY_OUTBOX_MAX_ATTEMPTS,
        processing_timeout_seconds: int = MEMORY_OUTBOX_PROCESSING_TIMEOUT_SECONDS,
    ) -> None:
        self.store = store or MemoryVectorStore()
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self.processing_timeout = timedelta(seconds=processing_timeout_seconds)

    async def close(self) -> None:
        self.store.close()

    # ------------------------------------------------------------------
    # Stale processing recovery
    # ------------------------------------------------------------------
    async def recover_stale_processing(self) -> int:
        """Reset stale PROCESSING events back to PENDING.

        Returns count of recovered events.
        """
        cutoff = _now() - self.processing_timeout
        async with async_session() as session:
            try:
                stmt = (
                    select(MemoryIndexOutbox)
                    .where(MemoryIndexOutbox.status == MemoryOutboxStatus.PROCESSING.value)
                    .where(MemoryIndexOutbox.updated_at <= cutoff)
                    .with_for_update(skip_locked=True)
                    .limit(self.batch_size)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                for row in rows:
                    row.status = MemoryOutboxStatus.PENDING.value
                    row.attempt_count = row.attempt_count + 1
                    row.last_error = "recovered from stale PROCESSING"
                await session.commit()
                recovered = len(rows)
                if recovered:
                    logger.info("Recovered %s stale PROCESSING outbox events", recovered)
                return recovered
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.error("Failed to recover stale processing events: %s", exc)
                return 0

    # ------------------------------------------------------------------
    # Claim eligible events
    # ------------------------------------------------------------------
    async def _claim_events(self, session: AsyncSession) -> List[MemoryIndexOutbox]:
        """Claim eligible outbox events for processing.

        Uses FOR UPDATE SKIP LOCKED so multiple workers can coexist safely.
        Eligible = PENDING or retryable FAILED.
        """
        eligible_statuses = [
            MemoryOutboxStatus.PENDING.value,
        ]
        retryable_failed = and_(
            MemoryIndexOutbox.status == MemoryOutboxStatus.FAILED.value,
            MemoryIndexOutbox.attempt_count < self.max_attempts,
        )
        stmt = (
            select(MemoryIndexOutbox)
            .where(or_(*[MemoryIndexOutbox.status == s for s in eligible_statuses], retryable_failed))
            .order_by(MemoryIndexOutbox.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(self.batch_size)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    # ------------------------------------------------------------------
    # Canonical memory loading
    # ------------------------------------------------------------------
    async def _load_canonical_memory(self, session: AsyncSession, memory_id: str) -> Optional[ConversationMemory]:
        stmt = select(ConversationMemory).where(ConversationMemory.id == memory_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Process one event against current canonical state
    # ------------------------------------------------------------------
    async def _process_event(self, session: AsyncSession, event: MemoryIndexOutbox) -> None:
        memory = await self._load_canonical_memory(session, event.memory_id)

        # Canonical-state-driven decision
        if memory is None or not _is_indexable(memory):
            desired_action = "DELETE"
        else:
            desired_action = "UPSERT"

        try:
            self.store.ensure_collection()
        except RuntimeError as exc:
            raise RuntimeError(f"Memory Qdrant collection setup failed: {exc}") from exc

        if desired_action == "DELETE":
            self.store.delete_point(event.memory_id)
            event.status = MemoryOutboxStatus.PROCESSED.value
            event.processed_at = _now()
            event.last_error = None
            return

        # UPSERT active canonical memory
        if memory is None:
            raise RuntimeError("Canonical memory missing for UPSERT")

        from rag.models.embeddings import LocalEmbedder, EmbeddingModelUnavailable
        try:
            embedder = LocalEmbedder(settings.EMBEDDING_MODEL)
        except EmbeddingModelUnavailable as exc:
            raise RuntimeError(f"Local embedding model unavailable: {exc}") from exc

        vector = embedder.embed([memory.content or ""])[0]
        if len(vector) != settings.MEMORY_EMBEDDING_DIM:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {settings.MEMORY_EMBEDDING_DIM}, got {len(vector)}"
            )

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
        event.status = MemoryOutboxStatus.PROCESSED.value
        event.processed_at = _now()
        event.last_error = None

    # ------------------------------------------------------------------
    # Run one processing batch
    # ------------------------------------------------------------------
    async def run_batch(self) -> Dict[str, int]:
        summary = {"processed": 0, "failed": 0, "skipped": 0}
        await self.recover_stale_processing()
        async with async_session() as session:
            try:
                events = await self._claim_events(session)
                if not events:
                    return summary
                # Mark events PROCESSING and commit to release row locks quickly
                for event in events:
                    event.status = MemoryOutboxStatus.PROCESSING.value
                    event.attempt_count = event.attempt_count + 1
                await session.commit()
            except SQLAlchemyError as exc:
                await session.rollback()
                logger.error("Failed to claim outbox events: %s", exc)
                return summary

            for event in events:
                try:
                    await self._process_event(session, event)
                    await session.commit()
                    summary["processed"] += 1
                except Exception as exc:
                    await session.rollback()
                    event.status = MemoryOutboxStatus.FAILED.value
                    event.last_error = str(exc)[:1024]
                    try:
                        await session.commit()
                    except SQLAlchemyError:
                        await session.rollback()
                    summary["failed"] += 1
                    logger.warning("Outbox event %s failed: %s", event.id, exc)
        return summary

    # ------------------------------------------------------------------
    # Continuous loop
    # ------------------------------------------------------------------
    async def run_loop(self, poll_seconds: float = 5.0, stop_on_error: bool = False) -> None:
        import asyncio
        logger.info(
            "Memory outbox loop started (batch=%s, poll=%ss)",
            self.batch_size,
            poll_seconds,
        )
        try:
            while True:
                try:
                    summary = await self.run_batch()
                    if summary["processed"] or summary["failed"]:
                        logger.info("Outbox batch: %s", summary)
                except Exception as exc:
                    if stop_on_error:
                        raise
                    logger.error("Outbox batch error: %s", exc, exc_info=True)
                await asyncio.sleep(poll_seconds)
        finally:
            await self.close()
