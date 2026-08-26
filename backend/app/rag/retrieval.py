import logging
from typing import List, Dict, Any, Optional

from app.rag.dense import dense_retriever
from app.rag.sparse import bm25_retriever
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.reranker import reranker

logger = logging.getLogger(__name__)


async def hybrid_search(
    query: str,
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    doc_type_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Perform hybrid search combining dense and sparse retrieval with RRF and reranking.

    Pipeline:
    1. Dense retrieval (embeddings + Qdrant)
    2. Sparse retrieval (BM25)
    3. RRF fusion
    4. Local reranking

    Args:
        query: Search query
        top_k: Number of results to return
        filters: Optional filters for retrieval

    Returns:
        List of relevant chunks with scores
    """
    logger.info(f"Hybrid search for query: {query}")

    try:
        dense_results = await dense_retriever.search(query, top_k=top_k * 2)
        logger.info(f"Dense retrieval returned {len(dense_results)} results")
    except Exception as e:
        logger.error(f"Dense retrieval error: {e}")
        dense_results = []

    try:
        sparse_results = bm25_retriever.search(query, top_k=top_k * 2)
        logger.info(f"Sparse retrieval returned {len(sparse_results)} results")
    except Exception as e:
        logger.error(f"Sparse retrieval error: {e}")
        sparse_results = []

    if not dense_results and not sparse_results:
        logger.warning("No results from either retrieval method")
        return []

    fused_results = reciprocal_rank_fusion(dense_results, sparse_results)
    logger.info(f"RRF fusion returned {len(fused_results)} results")

    try:
        reranked_results = await reranker.rerank(query, fused_results, top_k=top_k * 2 if doc_type_filter else top_k)
        logger.info(f"Reranking returned {len(reranked_results)} results")
    except Exception as e:
        logger.error(f"Reranking error: {e}")
        reranked_results = fused_results[:top_k * 2] if doc_type_filter else fused_results[:top_k]

    if doc_type_filter:
        reranked_results = [
            r for r in reranked_results
            if r.get("metadata", {}).get("doc_type") == doc_type_filter
        ][:top_k]

    return reranked_results
