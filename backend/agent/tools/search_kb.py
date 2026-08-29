"""Tool: search_knowledge_base

Thin, typed wrapper over the existing Phase 3 local hybrid RAG
(Qdrant + BM25, sentence-transformers, fully offline). Returns a flat list with
the exact fields the agent contract requires.
"""
import logging
from typing import List, Dict, Any, Optional

from rag.retrieval.hybrid import get_retriever

logger = logging.getLogger(__name__)

_RETRIEVER = None


def _get_retriever():
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = get_retriever()
    return _RETRIEVER


def search_knowledge_base(
    query: str,
    asset_tag: Optional[str] = None,
    document_type: Optional[str] = None,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    """Hybrid retrieve from the local knowledge base.

    Returns a list of dicts with keys:
        text, source_file, document_type, asset_tag, data_origin, score
    """
    res = _get_retriever().retrieve(query, asset_tag=asset_tag,
                                    document_type=document_type, top_k=top_k)
    out: List[Dict[str, Any]] = []
    for r in res:
        m = r.get("metadata", {})
        out.append({
            "text": r.get("text", ""),
            "source_file": m.get("source_file", ""),
            "document_type": m.get("document_type", ""),
            "asset_tag": m.get("asset_tag", ""),
            "data_origin": m.get("data_origin", ""),
            "score": r.get("score", 0.0),
            "chunk_id": m.get("chunk_id", ""),
            "section": m.get("section", ""),
        })
    return out
