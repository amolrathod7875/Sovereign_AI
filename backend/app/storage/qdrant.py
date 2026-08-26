import logging
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from typing import List, Dict, Any, Optional
import uuid

from app.config import settings

logger = logging.getLogger(__name__)

client: Optional[QdrantClient] = None

COLLECTION_NAME = "sovereign_rag"


async def init_qdrant():
    global client
    try:
        client = QdrantClient(url=settings.QDRANT_URL)
        collections = client.get_collections().collections
        if COLLECTION_NAME not in [c.name for c in collections]:
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")
        else:
            logger.info(f"Qdrant collection already exists: {COLLECTION_NAME}")
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant: {e}")
        client = None


def get_client() -> Optional[QdrantClient]:
    return client


async def insert_chunk(
    document_id: str,
    chunk_id: str,
    text: str,
    vector: List[float],
    metadata: Dict[str, Any],
):
    if not client:
        logger.warning("Qdrant client not initialized")
        return

    point = PointStruct(
        id=chunk_id,
        vector=vector,
        payload={
            "document_id": document_id,
            "text": text,
            "metadata": metadata,
        },
    )

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[point],
    )


async def search_chunks(
    query_vector: List[float],
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    if not client:
        logger.warning("Qdrant client not initialized")
        return []

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=top_k,
        query_filter=filters,
    )

    return [
        {
            "chunk_id": hit.id,
            "score": hit.score,
            "text": hit.payload.get("text"),
            "document_id": hit.payload.get("document_id"),
            "metadata": hit.payload.get("metadata"),
        }
        for hit in results
    ]


async def get_document_chunks(document_id: str) -> List[Dict[str, Any]]:
    if not client:
        return []

    results = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter={"must": [{"key": "document_id", "match": {"value": document_id}}]},
        limit=1000,
    )

    return [
        {
            "chunk_id": hit.id,
            "text": hit.payload.get("text"),
            "metadata": hit.payload.get("metadata"),
        }
        for hit in results[0]
    ]


async def delete_document_chunks(document_id: str):
    if not client:
        return

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector={
            "filter": {"must": [{"key": "document_id", "match": {"value": document_id}}]}
        },
    )
