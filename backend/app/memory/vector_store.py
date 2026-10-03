"""Dedicated memory vector store for the M5 semantic memory index.

PostgreSQL remains canonical truth. This store is a derived search index only.
It uses a separate embedded Qdrant path from the industrial RAG store to avoid
lock conflicts and accidental cross-system mutation.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, Filter, PointStruct, VectorParams

from app.config import settings
from app.memory.index_config import (
    MEMORY_EMBEDDING_DIM,
    MEMORY_QDRANT_COLLECTION,
    MEMORY_QDRANT_PATH,
)

logger = logging.getLogger(__name__)


def _stable_point_id(memory_id: str) -> str:
    """Derive a stable Qdrant point id from canonical memory_id.

    M4 memory_id values are UUID strings, which Qdrant accepts directly.
    If a non-UUID is ever provided, fall back to UUID5 for determinism.
    """
    try:
        uuid.UUID(memory_id)
        return memory_id
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"memory:{memory_id}"))


class MemoryVectorStore:
    """Local embedded Qdrant vector store for semantic memory index.

    Responsibilities:
      * manage sovereign_memory collection on a separate Qdrant path
      * UPSERT / DELETE points keyed by canonical memory_id
      * expose minimal diagnostics
    """

    def __init__(self, path: Optional[str] = None, collection: Optional[str] = None) -> None:
        self.path = Path(path or MEMORY_QDRANT_PATH)
        self.collection = collection or MEMORY_QDRANT_COLLECTION
        self._client: Optional[QdrantClient] = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self.path.mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=str(self.path))
        return self._client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def ensure_collection(self, expected_dim: int = MEMORY_EMBEDDING_DIM) -> None:
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection not in existing:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=expected_dim, distance=Distance.COSINE),
            )
            logger.info("Created memory Qdrant collection %s (dim=%s)", self.collection, expected_dim)
            return
        actual = self._get_collection_dim()
        if actual is not None and actual != expected_dim:
            raise RuntimeError(
                "Memory Qdrant collection dimension mismatch: "
                f"expected {expected_dim}, found {actual} for collection {self.collection}. "
                "Do not destroy production index automatically."
            )
        logger.debug("Memory Qdrant collection %s already exists (dim=%s)", self.collection, actual)

    def _get_collection_dim(self) -> Optional[int]:
        try:
            info = self.client.get_collection(self.collection)
            params = getattr(info.config, "params", None)
            vec_config = getattr(params, "vectors", None)
            if vec_config is None:
                vec_config = getattr(params, "vectors_config", None)
            if vec_config is not None:
                if hasattr(vec_config, "size"):
                    return int(vec_config.size)
                if hasattr(vec_config, "vec_size"):
                    return int(vec_config.vec_size)
            cfg = info.model_dump()
            v = cfg.get("config", {}).get("params", {}).get("vectors", {})
            if isinstance(v, dict):
                first = next(iter(v.values()))
                return int(first.get("size"))
        except Exception:
            pass
        return None

    def upsert_point(self, memory_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        point_id = _stable_point_id(memory_id)
        self.client.upsert(
            collection_name=self.collection,
            points=[
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            ],
        )

    def delete_point(self, memory_id: str) -> None:
        point_id = _stable_point_id(memory_id)
        try:
            self.client.delete(collection_name=self.collection, points_selector=[point_id])
        except KeyError:
            pass

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        qdrant_filter: Optional[Filter] = None,
    ) -> List[Dict[str, Any]]:
        hits = self.client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
        )
        results: List[Dict[str, Any]] = []
        for hit in hits:
            results.append(
                {
                    "point_id": hit.id,
                    "score": float(hit.score),
                    "payload": hit.payload or {},
                }
            )
        return results

    def point_count(self) -> int:
        try:
            info = self.client.get_collection(self.collection)
            return int(getattr(info, "points_count", 0) or 0)
        except Exception:
            return 0

    def collection_exists(self) -> bool:
        existing = {c.name for c in self.client.get_collections().collections}
        return self.collection in existing

    def __enter__(self) -> MemoryVectorStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
