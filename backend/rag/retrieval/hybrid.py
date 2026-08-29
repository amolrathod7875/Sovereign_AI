"""Hybrid retrieval: semantic (Qdrant cosine) + BM25 lexical, score-normalized, weighted fusion.

retrieve(query, asset_tag, document_type, top_k) -> list of
  {"text", "score", "metadata": {asset_tag, document_type, source_file, data_origin,
                                  source_drawing, chunk_id}}
"""
import logging
from typing import List, Dict, Any, Optional

from rag import config
from rag.models.embeddings import LocalEmbedder
from rag.indexing.qdrant_store import QdrantStore
from rag.indexing.bm25_store import BM25Store

logger = logging.getLogger("rag.retrieval")


def _normalize(scores: List[float]) -> List[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [1.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


class HybridRetriever:
    def __init__(self):
        self.embedder = LocalEmbedder(config.EMBEDDING_MODEL)
        self.qstore = QdrantStore()
        self.bm = BM25Store()

    def retrieve(self, query: str, asset_tag: str = None, document_type: str = None,
                 top_k: int = 8) -> List[Dict[str, Any]]:
        qvec = self.embedder.embed([query])[0]

        sem = self.qstore.search(qvec, top_k=top_k * 4, asset_tag=asset_tag,
                                 document_type=document_type)
        lex = self.bm.search(query, top_k=top_k * 4, asset_tag=asset_tag,
                            document_type=document_type)

        fused: Dict[str, Dict[str, Any]] = {}
        for hit, n in zip(sem, _normalize([h["score"] for h in sem])):
            fused[hit["chunk_id"]] = {
                "text": hit["text"], "metadata": hit["metadata"], "score": config.SEMANTIC_WEIGHT * n,
            }
        for hit, n in zip(lex, _normalize([h["score"] for h in lex])):
            cur = fused.get(hit["chunk_id"])
            if cur is None:
                fused[hit["chunk_id"]] = {
                    "text": hit["text"], "metadata": hit["metadata"],
                    "score": config.BM25_WEIGHT * n,
                }
            else:
                cur["score"] += config.BM25_WEIGHT * n

        ordered = sorted(fused.values(), key=lambda x: x["score"], reverse=True)[:top_k]
        return [{"text": o["text"], "score": round(o["score"], 4), "metadata": o["metadata"]}
                for o in ordered]


_RETRIEVER = None


def get_retriever() -> HybridRetriever:
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = HybridRetriever()
    return _RETRIEVER


def format_provenance(metadata: Dict[str, Any]) -> str:
    return (
        f"[Source: {metadata.get('asset_tag')} / {metadata.get('document_type')}]\n"
        f"[Document type: {metadata.get('document_type')}]\n"
        f"[Source file: {metadata.get('source_file')}]\n"
        f"[Data origin: {metadata.get('data_origin')}]"
    )
