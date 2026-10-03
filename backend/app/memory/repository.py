"""SQLAlchemy async repository for canonical conversation memories.

This module owns every direct database interaction for:
  * conversation_memories
  * memory_provenance
  * memory_index_outbox
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, func, desc, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.identity.principal import Principal
from app.memory.schemas import (
    MemoryScope,
    MemoryType,
    MemoryOutboxOperation,
    MemoryOutboxStatus,
)
from app.memory.normalization import normalize_memory_content
from app.storage.postgres import (
    async_session,
    Organization,
    User,
    Conversation,
    Message,
    ConversationSummaryRecord,
    ConversationMemory,
    MemoryProvenance,
    MemoryIndexOutbox,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------
from dataclasses import dataclass
from typing import Optional as Opt


@dataclass
class MemoryCandidate:
    memory_type: str
    scope: str
    content: str
    importance: float
    confidence: float


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
class MemoryRepository:
    """Async repository for canonical memory operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Deduplication lookup
    # ------------------------------------------------------------------
    async def find_existing_active(
        self,
        principal: Principal,
        scope: str,
        memory_type: str,
        normalized_content: str,
    ) -> Opt[ConversationMemory]:
        stmt = (
            select(ConversationMemory)
            .where(ConversationMemory.organization_id == principal.organization_id)
            .where(ConversationMemory.active == True)
            .where(ConversationMemory.scope == scope)
            .where(ConversationMemory.memory_type == memory_type)
            .where(ConversationMemory.normalized_content == normalized_content)
        )
        if scope == MemoryScope.PERSONAL.value:
            stmt = stmt.where(ConversationMemory.user_id == principal.user_id)
        elif scope == MemoryScope.CONVERSATION.value:
            stmt = stmt.where(ConversationMemory.user_id == principal.user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Create memory + provenance + outbox atomically
    # ------------------------------------------------------------------
    async def create_memory_with_provenance(
        self,
        principal: Principal,
        candidate: MemoryCandidate,
        source_message_id: Opt[str] = None,
        source_conversation_id: Opt[str] = None,
        conversation_id: Opt[str] = None,
        supersedes_memory_id: Opt[str] = None,
    ) -> ConversationMemory:
        import uuid
        memory_id = str(uuid.uuid4())
        normalized = normalize_memory_content(candidate.content)
        memory = ConversationMemory(
            id=memory_id,
            organization_id=principal.organization_id,
            user_id=principal.user_id if candidate.scope in (MemoryScope.PERSONAL.value, MemoryScope.CONVERSATION.value) else None,
            conversation_id=conversation_id if candidate.scope == MemoryScope.CONVERSATION.value else None,
            scope=candidate.scope,
            memory_type=candidate.memory_type,
            content=candidate.content,
            normalized_content=normalized,
            importance=float(candidate.importance),
            confidence=float(candidate.confidence),
            source_message_id=source_message_id,
            source_conversation_id=source_conversation_id,
            active=True,
            version=1,
            supersedes_memory_id=supersedes_memory_id,
        )
        self.session.add(memory)

        # Provenance
        prov = MemoryProvenance(
            id=str(uuid.uuid4()),
            memory_id=memory_id,
            source_message_id=source_message_id,
            source_conversation_id=source_conversation_id,
            organization_id=principal.organization_id,
            user_id=principal.user_id,
        )
        self.session.add(prov)

        # Outbox
        outbox = MemoryIndexOutbox(
            id=str(uuid.uuid4()),
            memory_id=memory_id,
            operation=MemoryOutboxOperation.UPSERT.value,
            status=MemoryOutboxStatus.PENDING.value,
        )
        self.session.add(outbox)

        return memory

    # ------------------------------------------------------------------
    # Supersede old memory
    # ------------------------------------------------------------------
    async def supersede_memory(
        self,
        principal: Principal,
        old_memory: ConversationMemory,
        candidate: MemoryCandidate,
        source_message_id: Opt[str] = None,
        source_conversation_id: Opt[str] = None,
        conversation_id: Opt[str] = None,
    ) -> ConversationMemory:
        old_memory.active = False
        self.session.add(old_memory)

        # Outbox DELETE for old memory
        import uuid
        old_outbox = MemoryIndexOutbox(
            id=str(uuid.uuid4()),
            memory_id=old_memory.id,
            operation=MemoryOutboxOperation.DELETE.value,
            status=MemoryOutboxStatus.PENDING.value,
        )
        self.session.add(old_outbox)

        # Create new memory
        new_memory = await self.create_memory_with_provenance(
            principal=principal,
            candidate=candidate,
            source_message_id=source_message_id,
            source_conversation_id=source_conversation_id,
            conversation_id=conversation_id,
            supersedes_memory_id=old_memory.id,
        )
        return new_memory

    # ------------------------------------------------------------------
    # Add provenance to existing memory (dedup case)
    # ------------------------------------------------------------------
    async def add_provenance(
        self,
        memory: ConversationMemory,
        principal: Principal,
        source_message_id: Opt[str] = None,
        source_conversation_id: Opt[str] = None,
    ) -> None:
        import uuid
        prov = MemoryProvenance(
            id=str(uuid.uuid4()),
            memory_id=memory.id,
            source_message_id=source_message_id,
            source_conversation_id=source_conversation_id,
            organization_id=principal.organization_id,
            user_id=principal.user_id,
        )
        self.session.add(prov)

    # ------------------------------------------------------------------
    # Get single memory by id (with org + user ownership)
    # ------------------------------------------------------------------
    async def get_memory(
        self,
        principal: Principal,
        memory_id: str,
    ) -> Opt[ConversationMemory]:
        stmt = (
            select(ConversationMemory)
            .where(ConversationMemory.id == memory_id)
            .where(ConversationMemory.organization_id == principal.organization_id)
        )
        result = await self.session.execute(stmt)
        memory = result.scalar_one_or_none()
        if memory is None:
            return None
        if memory.scope == MemoryScope.PERSONAL.value and memory.user_id != principal.user_id:
            return None
        if memory.scope == MemoryScope.CONVERSATION.value:
            if memory.user_id != principal.user_id:
                return None
            if memory.conversation_id:
                conv = await self.validate_conversation_access(
                    principal, memory.conversation_id
                )
                if conv is None:
                    return None
        return memory

    # ------------------------------------------------------------------
    # Conversation ownership validation
    # ------------------------------------------------------------------
    async def validate_conversation_access(
        self,
        principal: Principal,
        conversation_id: str,
    ) -> Opt[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .where(Conversation.organization_id == principal.organization_id)
            .where(Conversation.owner_user_id == principal.user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Deactivate memory
    # ------------------------------------------------------------------
    async def deactivate_memory(
        self,
        principal: Principal,
        memory_id: str,
    ) -> Opt[ConversationMemory]:
        memory = await self.get_memory(principal, memory_id)
        if not memory:
            return None
        memory.active = False
        self.session.add(memory)

        import uuid
        outbox = MemoryIndexOutbox(
            id=str(uuid.uuid4()),
            memory_id=memory.id,
            operation=MemoryOutboxOperation.DELETE.value,
            status=MemoryOutboxStatus.PENDING.value,
        )
        self.session.add(outbox)
        return memory

    # ------------------------------------------------------------------
    # List active memories
    # ------------------------------------------------------------------
    async def list_active_memories(
        self,
        principal: Principal,
        scope: Opt[str] = None,
        memory_type: Opt[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ConversationMemory]:
        stmt = (
            select(ConversationMemory)
            .where(ConversationMemory.organization_id == principal.organization_id)
            .where(ConversationMemory.active == True)
        )
        if scope:
            stmt = stmt.where(ConversationMemory.scope == scope)
            if scope in (MemoryScope.PERSONAL.value, MemoryScope.CONVERSATION.value):
                stmt = stmt.where(ConversationMemory.user_id == principal.user_id)
        else:
            stmt = stmt.where(
                or_(
                    ConversationMemory.scope == MemoryScope.ORGANIZATION.value,
                    ConversationMemory.user_id == principal.user_id,
                )
            )
        if memory_type:
            stmt = stmt.where(ConversationMemory.memory_type == memory_type)
        stmt = stmt.order_by(desc(ConversationMemory.updated_at)).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_memories(
        self,
        principal: Principal,
        scope: Opt[str] = None,
        memory_type: Opt[str] = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ConversationMemory)
            .where(ConversationMemory.organization_id == principal.organization_id)
            .where(ConversationMemory.active == True)
        )
        if scope:
            stmt = stmt.where(ConversationMemory.scope == scope)
            if scope in (MemoryScope.PERSONAL.value, MemoryScope.CONVERSATION.value):
                stmt = stmt.where(ConversationMemory.user_id == principal.user_id)
        else:
            stmt = stmt.where(
                or_(
                    ConversationMemory.scope == MemoryScope.ORGANIZATION.value,
                    ConversationMemory.user_id == principal.user_id,
                )
            )
        if memory_type:
            stmt = stmt.where(ConversationMemory.memory_type == memory_type)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    # ------------------------------------------------------------------
    # Count provenance rows for a memory
    # ------------------------------------------------------------------
    async def count_provenance(self, memory_id: str) -> int:
        stmt = select(func.count(MemoryProvenance.id)).where(MemoryProvenance.memory_id == memory_id)
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    # ------------------------------------------------------------------
    # Remove provenance for a specific conversation
    # ------------------------------------------------------------------
    async def remove_provenance_for_conversation(
        self,
        conversation_id: str,
    ) -> List[MemoryProvenance]:
        stmt = select(MemoryProvenance).where(MemoryProvenance.source_conversation_id == conversation_id)
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        for row in rows:
            await self.session.delete(row)
        return rows

    # ------------------------------------------------------------------
    # Get memories with zero provenance
    # ------------------------------------------------------------------
    async def find_memories_with_zero_provenance(self) -> List[ConversationMemory]:
        subq = (
            select(MemoryProvenance.memory_id)
            .group_by(MemoryProvenance.memory_id)
            .having(func.count(MemoryProvenance.id) > 0)
            .subquery()
        )
        stmt = (
            select(ConversationMemory)
            .where(ConversationMemory.active == True)
            .where(ConversationMemory.id.not_in(subq))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Outbox queries
    # ------------------------------------------------------------------
    async def list_outbox_for_memory(self, memory_id: str) -> List[MemoryIndexOutbox]:
        stmt = (
            select(MemoryIndexOutbox)
            .where(MemoryIndexOutbox.memory_id == memory_id)
            .order_by(desc(MemoryIndexOutbox.created_at))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
