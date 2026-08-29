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
