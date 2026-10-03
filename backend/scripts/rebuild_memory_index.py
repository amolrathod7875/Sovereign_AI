#!/usr/bin/env python3
"""M5 memory index rebuild CLI.

Rebuilds the sovereign_memory Qdrant collection from canonical PostgreSQL active memories.

Examples:
  python scripts/rebuild_memory_index.py --dry-run
  python scripts/rebuild_memory_index.py
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def _rebuild(dry_run: bool, force: bool) -> int:
    from app.memory.index_config import MEMORY_QDRANT_COLLECTION, MEMORY_EMBEDDING_DIM
    from app.memory.vector_store import MemoryVectorStore
    from app.storage.postgres import async_session, ConversationMemory
    from sqlalchemy import select

    store = MemoryVectorStore()
    try:
        store.ensure_collection(expected_dim=MEMORY_EMBEDDING_DIM)
    except RuntimeError as exc:
        print(f"Collection setup failed: {exc}")
        return 1

    async with async_session() as session:
        stmt = (
            select(ConversationMemory)
            .where(ConversationMemory.active == True)
            .where(
                (ConversationMemory.expires_at.is_(None)) | (ConversationMemory.expires_at > datetime.utcnow())
            )
        )
        result = await session.execute(stmt)
        memories = result.scalars().all()

    print(f"Canonical active non-expired memories: {len(memories)}")

    if dry_run:
        print("Dry-run: no Qdrant mutations.")
        return 0

    from rag.models.embeddings import LocalEmbedder, EmbeddingModelUnavailable
    from app.config import settings
    try:
        embedder = LocalEmbedder(settings.EMBEDDING_MODEL)
    except EmbeddingModelUnavailable as exc:
        print(f"Embedding model unavailable: {exc}")
        return 1

    count = 0
    for memory in memories:
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
        store.upsert_point(memory.id, vector, payload)
        count += 1

    print(f"Upserted {count} memory points into {MEMORY_QDRANT_COLLECTION}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="M5 memory index rebuild")
    parser.add_argument("--dry-run", action="store_true", help="Show canonical count without mutating Qdrant")
    parser.add_argument("--force", action="store_true", help="Force recreation (not implemented; kept for future)")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()
    configure_logging(args.verbose)
    return asyncio.run(_rebuild(dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    sys.exit(main())
