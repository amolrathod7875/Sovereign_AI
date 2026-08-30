"""Knowledge-base retrieval surface.

Phase 6 integration fix: this endpoint previously called
``app.rag.retrieval.hybrid_search``, which is the placeholder path documented in
``reports/phase5d_architecture.md`` §3 — its dense stage uses **random** embeddings,
so any evidence shown in the UI would have been meaningless. It now calls the same
authoritative retriever the LangGraph agent uses:

    app/api/rag.py  ->  agent.tools.search_kb.search_knowledge_base
                    ->  rag.retrieval.hybrid.HybridRetriever
                        (embedded Qdrant `sovereign_knowledge` + local BM25 +
                         offline sentence-transformers)

No second RAG system is introduced; the mock module is simply no longer used.
"""
import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class RAGSearchRequest(BaseModel):
    query: str
    top_k: int = 8
    asset_tag: Optional[str] = None
    document_type: Optional[str] = None
    # Retained for backwards compatibility: {"asset_tag": ..., "document_type": ...}
    filters: Optional[dict] = None


class RAGSearchResult(BaseModel):
    """One retrieved chunk with the provenance the local index actually stores."""

    chunk_id: str
    text: str
    document_type: str
    source_file: str
    asset_tag: str = ""
    data_origin: str = ""
    section: str = ""
    score: float


class RAGSearchResponse(BaseModel):
    query: str
    retriever: str
    results: List[RAGSearchResult]
    count: int


@router.post("/search", response_model=RAGSearchResponse)
async def search_knowledge(request: RAGSearchRequest) -> RAGSearchResponse:
    filters = request.filters or {}
    asset_tag = request.asset_tag or filters.get("asset_tag")
    document_type = request.document_type or filters.get("document_type")

    if not (request.query or "").strip():
        raise HTTPException(status_code=422, detail="query must not be empty")

    try:
        from agent.tools.search_kb import search_knowledge_base
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Local knowledge base retriever unavailable: {e}",
        )

    try:
        # Retrieval loads a local embedding model + embedded Qdrant; run off-loop.
        hits = await asyncio.to_thread(
            search_knowledge_base,
            request.query,
            asset_tag,
            document_type,
            request.top_k,
        )
    except FileNotFoundError as e:
        # BM25 / Qdrant index not built yet — report it precisely, do not fake hits.
        raise HTTPException(
            status_code=503,
            detail=f"Local knowledge index not built: {e}",
        )
    except Exception as e:
        logger.error("rag search failed: %s", e)
        raise HTTPException(status_code=500, detail=f"knowledge base search failed: {e}")

    results = [
        RAGSearchResult(
            chunk_id=h.get("chunk_id", ""),
            text=h.get("text", ""),
            document_type=h.get("document_type", ""),
            source_file=h.get("source_file", ""),
            asset_tag=h.get("asset_tag", ""),
            data_origin=h.get("data_origin", ""),
            section=h.get("section", ""),
            score=float(h.get("score", 0.0)),
        )
        for h in hits
    ]
    return RAGSearchResponse(
        query=request.query,
        retriever="hybrid (embedded Qdrant + BM25, local)",
        results=results,
        count=len(results),
    )


@router.get("/debug/{document_id}")
async def debug_document(document_id: str):
    from app.storage.qdrant import get_document_chunks

    chunks = await get_document_chunks(document_id)
    return {"document_id": document_id, "chunks": chunks}
