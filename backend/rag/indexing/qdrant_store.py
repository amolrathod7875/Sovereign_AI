"""Local embedded Qdrant store (no server, zero network).

Uses qdrant_client in on-disk mode via `path=`. Collection is dedicated to the
Sovereign AI knowledge base. Vectors + payload (text + metadata) are stored.
"""
import logging
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from rag import config

logger = logging.getLogger("rag.qdrant_store")


class QdrantStore:
    def __init__(self, collection: str = None, dim: int = None, path: Path = None):
        self.collection = collection or config.COLLECTION_NAME
        self.path = Path(path or config.QDRANT_PATH)
        self.path.mkdir(parents=True, exist_ok=True)
        self._client = QdrantClient(path=str(self.path))
        self._dim = dim

    @property
    def client(self) -> QdrantClient:
        return self._client

    def ensure_collection(self, dim: int):
        self._dim = dim
        existing = {c.name for c in self._client.get_collections().collections}
        if self.collection not in existing:
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection: {self.collection} (dim={dim})")
        else:
            logger.info(f"Qdrant collection exists: {self.collection}")

    def collection_dim(self) -> int:
        """Return the vector dimension of the existing collection, or None if absent."""
        existing = {c.name: c for c in self._client.get_collections().collections}
        if self.collection not in existing:
            return None
        info = self._client.get_collection(self.collection)
        # Qdrant exposes the configured vector size via get_collection_config in
        # newer clients; fall back to the collection info params.
        params = getattr(info.config, "params", None)
        vec_config = getattr(params, "vectors", None)
        if vec_config is None:
            vec_config = params.vectors_config if hasattr(params, "vectors_config") else None
        if vec_config is not None:
            if hasattr(vec_config, "size"):
                return int(vec_config.size)
            if hasattr(vec_config, "vec_size"):
                return int(vec_config.vec_size)
        # Last-resort: read from the top-level config dict
        try:
            cfg = self._client.get_collection(self.collection).model_dump()
            v = cfg.get("config", {}).get("params", {}).get("vectors", {})
            if isinstance(v, dict):
                first = next(iter(v.values()))
                return int(first.get("size"))
        except Exception:
            pass
        return None

    def upsert(self, points: List[Dict[str, Any]]):
        """points: list of {id (string chunk_id), vector, text, metadata}.

        Qdrant local mode requires UUID/int point ids, so we derive a stable UUID from
        the chunk_id; the original chunk_id is preserved in the payload + metadata.
        """
        pstructs = [
            PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_DNS, str(p["id"]))),
                        vector=p["vector"],
                        payload={"text": p["text"], **p["metadata"]})
            for p in points
        ]
        self._client.upsert(collection_name=self.collection, points=pstructs)

    def search(self, query_vector: List[float], top_k: int = 8,
               asset_tag: str = None, document_type: str = None) -> List[Dict[str, Any]]:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        must = []
        if asset_tag:
            must.append(FieldCondition(key="asset_tag", match=MatchValue(value=asset_tag)))
        if document_type:
            must.append(FieldCondition(key="document_type", match=MatchValue(value=document_type)))
        qf = Filter(must=must) if must else None
        hits = self._client.search(
            collection_name=self.collection, query_vector=query_vector,
            limit=top_k, query_filter=qf,
        )
        return [{
            "chunk_id": hit.id, "score": float(hit.score),
            "text": hit.payload.get("text"), "metadata": {
                "asset_tag": hit.payload.get("asset_tag"),
                "document_type": hit.payload.get("document_type"),
                "source_file": hit.payload.get("source_file"),
                "data_origin": hit.payload.get("data_origin"),
                "source_drawing": hit.payload.get("source_drawing"),
                "chunk_id": hit.payload.get("chunk_id"),
            },
        } for hit in hits]
