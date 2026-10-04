"""M4 memory API endpoints.

GET  /api/memory               — list active memories for the current principal
GET  /api/memory/{memory_id}   — get a single memory by id
DELETE /api/memory/{memory_id} — deactivate a memory (soft delete)
POST  /api/memory/extract-turn — extract durable memories from a completed turn (optional, for testing/manual trigger)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from sqlalchemy import select, func, desc

from app.config import settings
from app.identity.principal import Principal, get_current_principal_dep
from app.memory.schemas import MemoryScope, MemoryType
from app.memory.service import MemoryService
from app.memory.repository import MemoryRepository
from app.memory.search import MemorySemanticSearch, MemorySearchResponse
from app.storage.postgres import (
    async_session,
    Message,
    ConversationMemory,
    MemoryProvenance,
    MemoryIndexOutbox,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memory", tags=["memory"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------
class MemoryResponse(BaseModel):
    id: str
    scope: str
    memory_type: str
    content: str
    importance: float
    confidence: float
    active: bool
    version: int
    supersedes_memory_id: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    provenance_count: int = 0


class MemoryListResponse(BaseModel):
    memories: List[MemoryResponse] = Field(default_factory=list)
    total: int = 0


class ExtractTurnRequest(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str


class ExtractTurnResponse(BaseModel):
    processed: bool = False
    created: int = 0
    deduped: int = 0
    superseded: int = 0
    rejected: int = 0
    reason: Optional[str] = None


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1024)
    conversation_id: Optional[str] = None
    top_k: int = Field(5, ge=1, le=20)


class MemorySearchResultResponse(BaseModel):
    memory_id: str
    content: str
    scope: str
    memory_type: str
    semantic_score: float
    importance: float
    confidence: float
    conversation_id: Optional[str] = None
    version: int = 1
    updated_at: Optional[str] = None


class MemorySearchResponseModel(BaseModel):
    query: str
    results: List[MemorySearchResultResponse] = Field(default_factory=list)
    index: str = "sovereign_memory"
    retrieval_mode: str = "semantic_memory"
    embedding_local: bool = True
    candidate_count: int = 0
    returned_count: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _q(value):
    if hasattr(value, "default") and hasattr(value, "alias"):
        return value.default
    return value


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=MemoryListResponse)
async def list_memories(
    scope: Optional[str] = Query(None),
    memory_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(get_current_principal_dep),
):
    """List active memories for the current principal."""
    scope = _q(scope)
    memory_type = _q(memory_type)
    limit = _q(limit)
    offset = _q(offset)
    async with async_session() as session:
        repo = MemoryRepository(session)
        memories = await repo.list_active_memories(
            principal=principal,
            scope=scope,
            memory_type=memory_type,
            limit=limit,
            offset=offset,
        )
        total = await repo.count_memories(principal, scope=scope, memory_type=memory_type)

        memories_out = []
        for row in memories:
            prov_count = await repo.count_provenance(row.id)
            memories_out.append(
                MemoryResponse(
                    id=row.id,
                    scope=row.scope,
                    memory_type=row.memory_type,
                    content=row.content,
                    importance=row.importance,
                    confidence=row.confidence,
                    active=row.active,
                    version=row.version,
                    supersedes_memory_id=row.supersedes_memory_id,
                    expires_at=_iso(row.expires_at),
                    created_at=_iso(row.created_at),
                    updated_at=_iso(row.updated_at),
                    provenance_count=prov_count,
                )
            )
    return MemoryListResponse(memories=memories_out, total=total)


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    principal: Principal = Depends(get_current_principal_dep),
):
    """Get a single memory by ID."""
    async with async_session() as session:
        repo = MemoryRepository(session)
        memory = await repo.get_memory(principal, memory_id)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        prov_count = await repo.count_provenance(memory.id)
    return MemoryResponse(
        id=memory.id,
        scope=memory.scope,
        memory_type=memory.memory_type,
        content=memory.content,
        importance=memory.importance,
        confidence=memory.confidence,
        active=memory.active,
        version=memory.version,
        supersedes_memory_id=memory.supersedes_memory_id,
        expires_at=_iso(memory.expires_at),
        created_at=_iso(memory.created_at),
        updated_at=_iso(memory.updated_at),
        provenance_count=prov_count,
    )


@router.delete("/{memory_id}", response_model=dict)
async def delete_memory(
    memory_id: str,
    principal: Principal = Depends(get_current_principal_dep),
):
    """Deactivate a memory (soft delete)."""
    async with async_session() as session:
        repo = MemoryRepository(session)
        memory = await repo.deactivate_memory(principal, memory_id)
        if not memory:
            raise HTTPException(status_code=404, detail="Memory not found")
        await session.commit()
    return {"ok": True, "id": memory_id}


@router.post("/extract-turn", response_model=ExtractTurnResponse)
async def extract_turn(
    req: ExtractTurnRequest,
    principal: Principal = Depends(get_current_principal_dep),
):
    """Manually trigger memory extraction for a completed turn.

    This endpoint is optional and primarily for testing/manual triggers.
    The primary extraction path is automatic after assistant message persistence.
    """
    async with async_session() as session:
        # Verify messages exist and belong to the conversation
        user_msg = await session.get(Message, req.user_message_id)
        asst_msg = await session.get(Message, req.assistant_message_id)
        if not user_msg or not asst_msg:
            raise HTTPException(status_code=404, detail="Message not found")
        if user_msg.conversation_id != req.conversation_id or asst_msg.conversation_id != req.conversation_id:
            raise HTTPException(status_code=422, detail="Messages do not belong to the specified conversation")
        if asst_msg.role != "assistant":
            raise HTTPException(status_code=422, detail="Second message must be an assistant message")
        if asst_msg.status == "FAILED":
            raise HTTPException(status_code=422, detail="Cannot extract memory from a failed assistant turn")

        service = MemoryService(principal)
        summary = await service.process_turn(
            user_message_id=req.user_message_id,
            assistant_message_id=req.assistant_message_id,
            user_message_content=user_msg.content or "",
            assistant_message_content=asst_msg.content or "",
            conversation_id=req.conversation_id,
        )
        await session.commit()

    if summary is None:
        return ExtractTurnResponse(processed=False, reason="extraction skipped or failed")
    return ExtractTurnResponse(
        processed=True,
        created=summary.get("created", 0),
        deduped=summary.get("deduped", 0),
        superseded=summary.get("superseded", 0),
        rejected=summary.get("rejected", 0),
    )


@router.post("/search", response_model=MemorySearchResponseModel)
async def search_memories(
    req: MemorySearchRequest,
    principal: Principal = Depends(get_current_principal_dep),
):
    """Semantic memory search (M5 local Qdrant index + PostgreSQL canonical validation).

    M5 does not inject memories into model prompts. This endpoint only proves
    semantic retrieval exists. No General LLM generation is invoked.
    """
    search_service = MemorySemanticSearch()
    try:
        response = await search_service.search_memories(
            principal=principal,
            query=req.query,
            conversation_id=req.conversation_id,
            top_k=req.top_k,
        )
    finally:
        await search_service.close()
    return MemorySearchResponseModel(
        query=response.query,
        results=[
            MemorySearchResultResponse(
                memory_id=r.memory_id,
                content=r.content,
                scope=r.scope,
                memory_type=r.memory_type,
                semantic_score=r.semantic_score,
                importance=r.importance,
                confidence=r.confidence,
                conversation_id=r.conversation_id,
                version=r.version,
                updated_at=r.updated_at,
            )
            for r in response.results
        ],
        index=response.index,
        retrieval_mode=response.retrieval_mode,
        embedding_local=response.embedding_local,
        candidate_count=response.candidate_count,
        returned_count=response.returned_count,
    )
