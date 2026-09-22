"""Deterministic industrial asset-identity gate.

Identity is resolved from a local canonical asset registry only.  No embeddings,
no LLM, no fuzzy matching, no OCR-correction heuristics.

Registry source order
---------------------
1. ``SOVEREIGN_ASSET_REGISTRY`` env-var (JSON / JSONL / directory of profile.json)
2. ``data/synthetic/assets/`` directory (``*/profile.json`` with
   ``public_pid_identity.asset_tag``)

Normalization policy
--------------------
- trim whitespace
- uppercase
- collapse internal whitespace / separators ONLY when the result maps to exactly
  one known canonical tag

Forbidden
---------
- embedding similarity
- Levenshtein / edit distance
- LLM-based "is this the same?" reasoning
- silent character substitution (I->1, O->0, B->8, S->5, ...)
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence


class AssetIdentityStatus(str, Enum):
    VERIFIED = "VERIFIED"
    VERIFIED_TEXT_ONLY = "VERIFIED_TEXT_ONLY"
    CONFLICT = "CONFLICT"
    UNKNOWN_ASSET = "UNKNOWN_ASSET"
    MISSING_ASSET = "MISSING_ASSET"


@dataclass
class AssetIdentityResult:
    status: AssetIdentityStatus
    requested_tag: str
    canonical_tag: Optional[str] = None
    vision_tags: List[str] = field(default_factory=list)
    matched_vision_tag: Optional[str] = None
    related_vision_tags: List[str] = field(default_factory=list)
    reason: str = ""
    source: str = "local_asset_registry"


# ---------------------------------------------------------------------------
# Conservative normalization
# ---------------------------------------------------------------------------

# Canonical form: uppercase tag with optional single hyphen between letter
# prefix and numeric body, optional single trailing letter suffix.
# Examples: R-1001, P-2104A, TI-1001
_TAG_RE = re.compile(r"^([A-Z]{1,3})-?(\d{2,4})([A-Z])?$")


def _normalize_tag_candidate(raw: str) -> Optional[str]:
    """Return a canonical tag string or None if the input is not a plausible tag."""
    s = raw.strip().upper()
    m = _TAG_RE.match(s)
    if not m:
        return None
    prefix, number, suffix = m.groups()
    return f"{prefix}-{number}{suffix or ''}"


def normalize_asset_tag(raw: str, registry: Dict[str, dict]) -> Optional[str]:
    """Conservative normalization of a raw asset tag.

    Returns the canonical registry key if normalization resolves to exactly one
    known asset, otherwise None.
    """
    candidate = _normalize_tag_candidate(raw)
    if candidate is None:
        return None
    # Exact match first.
    if candidate in registry:
        return candidate
    # If the candidate is not in the registry, do NOT guess similar keys.
    return None


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

def _load_profile(path: Path) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        pid = data.get("public_pid_identity") or {}
        tag = pid.get("asset_tag")
        if not tag:
            return None
        return {
            "asset_tag": tag.strip().upper(),
            "plant": pid.get("plant", ""),
            "source_drawing": pid.get("source_drawing", ""),
            "data_origin": pid.get("data_origin", "local_asset_registry"),
        }
    except Exception:
        return None


def load_asset_registry(registry_dir: Optional[Path] = None) -> Dict[str, dict]:
    """Return ``{canonical_tag: metadata}`` from trusted local profile files."""
    registry: Dict[str, dict] = {}

    env = os.environ.get("SOVEREIGN_ASSET_REGISTRY")
    if env:
        p = Path(env)
        if p.is_file():
            candidates = [p]
        elif p.is_dir():
            candidates = sorted(p.glob("**/profile.json"))
        else:
            candidates = []
        for prof in candidates:
            meta = _load_profile(prof)
            if meta:
                registry[meta["asset_tag"]] = meta
        if registry:
            return registry

    if registry_dir is None:
        repo = Path(__file__).resolve().parents[2]
        registry_dir = repo / "data" / "synthetic" / "assets"

    if registry_dir.is_dir():
        for prof in sorted(registry_dir.glob("**/profile.json")):
            meta = _load_profile(prof)
            if meta:
                registry[meta["asset_tag"]] = meta

    return registry


# ---------------------------------------------------------------------------
# Identity resolution
# ---------------------------------------------------------------------------

def resolve_asset_identity(
    requested_tag: str,
    vision_tags: Optional[Sequence[str]] = None,
    registry: Optional[Dict[str, dict]] = None,
) -> AssetIdentityResult:
    """Validate the requested asset against the canonical registry and vision tags.

    Returns an AssetIdentityResult.  Never calls a model, never uses embeddings,
    never performs fuzzy matching.
    """
    if registry is None:
        registry = load_asset_registry()

    vision_tags = list(vision_tags or [])
    requested = requested_tag.strip().upper() if requested_tag else ""
    canonical = normalize_asset_tag(requested, registry) if requested else None

    if not requested:
        return AssetIdentityResult(
            status=AssetIdentityStatus.MISSING_ASSET,
            requested_tag=requested_tag or "",
            reason="Requested asset tag is empty.",
        )

    if canonical is None:
        return AssetIdentityResult(
            status=AssetIdentityStatus.UNKNOWN_ASSET,
            requested_tag=requested,
            reason=f"Requested asset '{requested_tag}' is not in the canonical registry.",
        )

    # Text-only path: no vision input.
    if not vision_tags:
        return AssetIdentityResult(
            status=AssetIdentityStatus.VERIFIED_TEXT_ONLY,
            requested_tag=requested,
            canonical_tag=canonical,
            reason=f"Requested asset '{requested}' is in the canonical registry (text-only task).",
        )

    # Vision path: check whether the canonical asset appears in validated vision tags.
    normalized_vision = []
    for vt in vision_tags:
        nc = _normalize_tag_candidate(vt)
        if nc is not None:
            normalized_vision.append(nc)

    matched = [t for t in normalized_vision if t == canonical]
    related = [t for t in normalized_vision if t != canonical]

    if matched:
        return AssetIdentityResult(
            status=AssetIdentityStatus.VERIFIED,
            requested_tag=requested,
            canonical_tag=canonical,
            vision_tags=normalized_vision,
            matched_vision_tag=matched[0],
            related_vision_tags=related,
            reason=(
                f"Requested asset '{requested}' verified: present in vision tags "
                f"({matched[0]}) and in the canonical registry."
            ),
        )

    # Canonical asset not found in vision tags but other known assets are present.
    return AssetIdentityResult(
        status=AssetIdentityStatus.CONFLICT,
        requested_tag=requested,
        canonical_tag=canonical,
        vision_tags=normalized_vision,
        matched_vision_tag=None,
        related_vision_tags=related,
        reason=(
            f"Requested asset '{requested}' is in the canonical registry but was NOT "
            f"found in vision tags. Vision observed: {normalized_vision}. "
            f"Refusing to proceed with asset-scoped retrieval."
        ),
    )
