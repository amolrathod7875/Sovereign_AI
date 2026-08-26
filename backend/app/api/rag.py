from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()


class RAGSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: Optional[dict] = None


class RAGSearchResult(BaseModel):
    chunk_id: str
    text: str
    document: str
    page: Optional[int] = None
    score: float
    source: str


@router.post("/search")
async def search_knowledge(request: RAGSearchRequest):
    from app.rag.retrieval import hybrid_search

    try:
        results = await hybrid_search(
            query=request.query,
            top_k=request.top_k,
            filters=request.filters,
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/{document_id}")
async def debug_document(document_id: str):
    from app.storage.qdrant import get_document_chunks

    chunks = await get_document_chunks(document_id)
    return {"document_id": document_id, "chunks": chunks}
