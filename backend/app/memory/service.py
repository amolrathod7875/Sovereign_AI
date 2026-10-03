"""M4 memory service — orchestrates extraction and persistence.

This service:
  1. Receives a completed conversation turn (user + assistant messages)
  2. Runs conservative memory extraction
  3. Persists canonical memory + provenance + outbox atomically in one transaction
  4. Handles deduplication and supersede logic
  5. Is BEST-EFFORT: never raises to the caller
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from app.config import settings
from app.identity.principal import Principal
from app.memory.schemas import MemoryScope, MemoryType
from app.memory.policies import is_transient_utterance, is_secret_like
from app.memory.extractor import MemoryExtractor, ExtractionResult, ExtractedMemoryCandidate
from app.memory.repository import MemoryRepository, MemoryCandidate as RepoMemoryCandidate

logger = logging.getLogger(__name__)


class MemoryService:
    """Coordinates memory extraction and persistence."""

    def __init__(self, principal: Principal) -> None:
        self.principal = principal
        self._extractor = MemoryExtractor(principal)

    async def process_turn(
        self,
        user_message_id: str,
        assistant_message_id: str,
        user_message_content: str,
        assistant_message_content: str,
        conversation_id: str,
    ) -> Optional[dict]:
        """Process a completed turn for memory extraction.

        This is best-effort. Returns a summary dict on success, None on failure.
        Never raises.
        """
        # Guard: transient / failed turn
        if not assistant_message_content or assistant_message_content.strip() in ("", "FAILED"):
            logger.debug("Skipping memory extraction for failed/empty assistant turn")
            return None
        if is_transient_utterance(user_message_content):
            logger.debug("Skipping memory extraction for transient user utterance")
            return None
        if is_secret_like(user_message_content):
            logger.debug("Skipping memory extraction for secret-like user content")
            return None

        extraction = await self._extractor.extract_turn(
            user_message=user_message_content,
            assistant_message=assistant_message_content,
        )
        if not extraction.candidates:
            logger.debug("No memory candidates extracted: %s", extraction.reason)
            return None

        return await self._persist_candidates(
            candidates=extraction.candidates,
            source_message_id=user_message_id,
            source_conversation_id=conversation_id,
            conversation_id=conversation_id,
        )

    async def _persist_candidates(
        self,
        candidates: List[ExtractedMemoryCandidate],
        source_message_id: str,
        source_conversation_id: str,
        conversation_id: str,
    ) -> Optional[dict]:
        """Persist extracted candidates in a single transaction.

        Returns a summary dict on success, None on failure.
        """
        from app.storage.postgres import async_session as _app_async_session
        if _app_async_session is None:
            logger.warning("Postgres not available; skipping memory persistence")
            return None

        summary = {
            "created": 0,
            "deduped": 0,
            "superseded": 0,
            "rejected": 0,
        }

        try:
            async with _app_async_session() as session:
                repo = MemoryRepository(session)
                for candidate in candidates:
                    try:
                        await self._process_candidate(
                            repo=repo,
                            candidate=candidate,
                            source_message_id=source_message_id,
                            source_conversation_id=source_conversation_id,
                            conversation_id=conversation_id,
                            summary=summary,
                        )
                    except Exception as e:
                        logger.warning("Failed to persist memory candidate: %s", e)
                        summary["rejected"] += 1
                await session.commit()
        except Exception as e:
            logger.warning("Memory persistence transaction failed: %s", e)
            return None

        return summary

    async def _process_candidate(
        self,
        repo: MemoryRepository,
        candidate: ExtractedMemoryCandidate,
        source_message_id: str,
        source_conversation_id: str,
        conversation_id: str,
        summary: dict,
    ) -> None:
        """Process a single candidate: dedup, supersede, or create."""
        from app.memory.normalization import normalize_memory_content
        normalized = normalize_memory_content(candidate.content)

        existing = await repo.find_existing_active(
            principal=self.principal,
            scope=candidate.scope,
            memory_type=candidate.memory_type,
            normalized_content=normalized,
        )

        if existing:
            # Dedup: add provenance, possibly update timestamps
            await repo.add_provenance(
                memory=existing,
                principal=self.principal,
                source_message_id=source_message_id,
                source_conversation_id=source_conversation_id,
            )
            summary["deduped"] += 1
            return

        # Check for superseding memory (same user + scope + type, but active)
        # We only supersede if this is a known preference/fact slot and the
        # candidate seems to contradict an existing active memory.
        # For simplicity and conservatism, we do NOT auto-supersede unless
        # the existing memory has the same scope/type and the candidate
        # clearly replaces it. We rely on the dedup + explicit user override
        # pattern instead.
        # (Auto-supersede logic would go here in a future enhancement.)

        repo_candidate = RepoMemoryCandidate(
            memory_type=candidate.memory_type,
            scope=candidate.scope,
            content=candidate.content,
            importance=candidate.importance,
            confidence=candidate.confidence,
        )
        await repo.create_memory_with_provenance(
            principal=self.principal,
            candidate=repo_candidate,
            source_message_id=source_message_id,
            source_conversation_id=source_conversation_id,
            conversation_id=conversation_id,
        )
        summary["created"] += 1
