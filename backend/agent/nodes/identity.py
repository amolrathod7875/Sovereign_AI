"""ASSET_IDENTITY node: deterministic industrial asset-identity gate.

Runs AFTER any vision analysis (if present) and BEFORE RAG retrieval.
Validates the requested asset against the canonical local asset registry and,
when vision input exists, confirms the requested asset is present in the
vision-extracted tags.

Blocked identity statuses halt the workflow safely with no RAG, no
calculations, and no approval artifact.
"""
import logging
import time
from typing import Dict, Any

from agent.identity import resolve_asset_identity, AssetIdentityStatus
from agent.utils import trace_entry, elapsed_ms

logger = logging.getLogger(__name__)


def run(state: dict) -> dict:
    start = time.time()
    requested = state.get("asset_tag", "")
    vision_tags = state.get("vision_tags") or []

    result = resolve_asset_identity(requested_tag=requested, vision_tags=vision_tags)

    blocked = result.status in (
        AssetIdentityStatus.CONFLICT,
        AssetIdentityStatus.UNKNOWN_ASSET,
        AssetIdentityStatus.MISSING_ASSET,
    )

    status_label = "IDENTITY_BLOCKED" if blocked else "IDENTITY_VERIFIED"

    return {
        "asset_identity": {
            "status": result.status.value,
            "requested_tag": result.requested_tag,
            "canonical_tag": result.canonical_tag,
            "vision_tags": result.vision_tags,
            "matched_vision_tag": result.matched_vision_tag,
            "related_vision_tags": result.related_vision_tags,
            "reason": result.reason,
            "source": result.source,
        },
        "status": status_label,
        "trace": [trace_entry(
            "asset_identity", result.status.value, "agent.identity",
            elapsed_ms(start), "BLOCKED" if blocked else "PASS",
            requested_tag=result.requested_tag,
            canonical_tag=result.canonical_tag,
            vision_match=result.matched_vision_tag,
            related_tag_count=len(result.related_vision_tags),
            vision_tags=result.vision_tags[:10],
        )],
    }
