import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(dense_results: List[Dict], sparse_results: List[Dict], k: int = 60) -> List[Dict]:
    """
    Fuse results from dense and sparse retrieval using Reciprocal Rank Fusion (RRF).

    RRF formula: score = sum(1 / (k + rank)) for each system that returns the item

    Args:
        dense_results: Results from dense retrieval
        sparse_results: Results from BM25 retrieval
        k: RRF smoothing parameter (default 60)

    Returns:
        Fused and re-ranked results
    """
    rrf_scores: Dict[str, Dict] = {}

    for rank, result in enumerate(dense_results):
        chunk_id = result["chunk_id"]
        score = 1 / (k + rank + 1)
        if chunk_id not in rrf_scores:
            rrf_scores[chunk_id] = {
                **result,
                "rrf_score": 0,
                "sources": ["dense"],
            }
        rrf_scores[chunk_id]["rrf_score"] += score

    for rank, result in enumerate(sparse_results):
        chunk_id = result["chunk_id"]
        score = 1 / (k + rank + 1)
        if chunk_id not in rrf_scores:
            rrf_scores[chunk_id] = {
                **result,
                "rrf_score": 0,
                "sources": ["sparse"],
            }
        else:
            rrf_scores[chunk_id]["sources"].append("sparse")
        rrf_scores[chunk_id]["rrf_score"] += score

    fused_results = list(rrf_scores.values())
    fused_results.sort(key=lambda x: x["rrf_score"], reverse=True)

    return fused_results
