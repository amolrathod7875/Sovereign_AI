"""Phase 14A1 — Industrial Asset Identity Guard Tests.

Tests the deterministic identity gate that must run BEFORE any RAG retrieval.
No GPU, no live model servers, no network calls.
"""
from __future__ import annotations

import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent.identity import (
    AssetIdentityStatus,
    normalize_asset_tag,
    resolve_asset_identity,
    load_asset_registry,
)
from agent.nodes.identity import run as identity_run
from agent.state import create_initial_state


# ---------------------------------------------------------------------------
# Registry fixtures
# ---------------------------------------------------------------------------

def _make_profile(tmp_path: Path, tag: str, plant: str = "Test Plant") -> Path:
    asset_dir = tmp_path / "assets" / tag
    asset_dir.mkdir(parents=True, exist_ok=True)
    prof = asset_dir / "profile.json"
    prof.write_text(json.dumps({
        "profile_version": "1.0.0",
        "public_pid_identity": {
            "asset_tag": tag,
            "plant": plant,
            "source_drawing": "test.jpg",
            "data_origin": "test",
        }
    }), encoding="utf-8")
    return prof


def _registry_with(tmp_path: Path, tags):
    for tag in tags:
        _make_profile(tmp_path, tag)
    return load_asset_registry(tmp_path)


# ---------------------------------------------------------------------------
# 1. Known exact asset resolves (text-only)
# ---------------------------------------------------------------------------
def test_known_exact_asset_text_only():
    registry = _registry_with(Path(tempfile.mkdtemp()), ["R-1001", "R-1002", "P-2104A", "P-2104B"])
    result = resolve_asset_identity(requested_tag="R-1001", vision_tags=None, registry=registry)
    assert result.status == AssetIdentityStatus.VERIFIED_TEXT_ONLY
    assert result.canonical_tag == "R-1001"


# ---------------------------------------------------------------------------
# 2. Case/whitespace normalization resolves safely
# ---------------------------------------------------------------------------
def test_case_whitespace_normalization():
    registry = _registry_with(Path(tempfile.mkdtemp()), ["R-1001"])
    result = resolve_asset_identity(requested_tag="  r-1001  ", vision_tags=None, registry=registry)
    assert result.status == AssetIdentityStatus.VERIFIED_TEXT_ONLY
    assert result.canonical_tag == "R-1001"


# ---------------------------------------------------------------------------
# 3. OCR-confusable tag is NOT corrected
# ---------------------------------------------------------------------------
def test_ocr_confusable_not_corrected():
    registry = _registry_with(Path(tempfile.mkdtemp()), ["R-1001"])
    result = resolve_asset_identity(requested_tag="R-100I", vision_tags=None, registry=registry)
    assert result.status == AssetIdentityStatus.UNKNOWN_ASSET
    assert result.canonical_tag is None


# ---------------------------------------------------------------------------
# 4. Similar numeric tag is NOT corrected
# ---------------------------------------------------------------------------
def test_similar_numeric_tag_not_corrected():
    registry = _registry_with(Path(tempfile.mkdtemp()), ["R-1001"])
    result = resolve_asset_identity(requested_tag="R-1002", vision_tags=None, registry=registry)
    assert result.status == AssetIdentityStatus.UNKNOWN_ASSET
    assert result.canonical_tag is None


# ---------------------------------------------------------------------------
# 5. P-2104A and P-2104B stay distinct
# ---------------------------------------------------------------------------
def test_p2104a_and_p2104b_distinct():
    registry = _registry_with(Path(tempfile.mkdtemp()), ["P-2104A", "P-2104B"])
    r_a = resolve_asset_identity(requested_tag="P-2104A", vision_tags=None, registry=registry)
    r_b = resolve_asset_identity(requested_tag="P-2104B", vision_tags=None, registry=registry)
    assert r_a.status == AssetIdentityStatus.VERIFIED_TEXT_ONLY
    assert r_b.status == AssetIdentityStatus.VERIFIED_TEXT_ONLY
    assert r_a.canonical_tag == "P-2104A"
    assert r_b.canonical_tag == "P-2104B"
    assert r_a.canonical_tag != r_b.canonical_tag


# ---------------------------------------------------------------------------
# 6. Vision exact match allows workflow
# ---------------------------------------------------------------------------
def test_vision_exact_match_allows_workflow():
    registry = _registry_with(Path(tempfile.mkdtemp()), ["R-1001"])
    result = resolve_asset_identity(
        requested_tag="R-1001",
        vision_tags=["R-1001", "TI-1001"],
        registry=registry,
    )
    assert result.status == AssetIdentityStatus.VERIFIED
    assert result.matched_vision_tag == "R-1001"
    assert "TI-1001" in result.related_vision_tags


# ---------------------------------------------------------------------------
# 7. Related tags do not create conflict
# ---------------------------------------------------------------------------
def test_related_tags_no_conflict():
    registry = _registry_with(Path(tempfile.mkdtemp()), ["R-1001"])
    result = resolve_asset_identity(
        requested_tag="R-1001",
        vision_tags=["R-1001", "TI-1001", "PI-1001"],
        registry=registry,
    )
    assert result.status == AssetIdentityStatus.VERIFIED
    assert set(result.related_vision_tags) == {"TI-1001", "PI-1001"}


# ---------------------------------------------------------------------------
# 8. Vision asset missing causes block
# ---------------------------------------------------------------------------
def test_vision_asset_missing_causes_block():
    registry = _registry_with(Path(tempfile.mkdtemp()), ["R-1001"])
    result = resolve_asset_identity(
        requested_tag="R-1001",
        vision_tags=["P-2104B", "XV-101"],
        registry=registry,
    )
    assert result.status == AssetIdentityStatus.CONFLICT
    assert result.canonical_tag == "R-1001"
    assert result.matched_vision_tag is None


# ---------------------------------------------------------------------------
# 9. Unknown requested asset blocks retrieval
# ---------------------------------------------------------------------------
def test_unknown_requested_asset_blocks():
    registry = _registry_with(Path(tempfile.mkdtemp()), ["R-1001"])
    result = resolve_asset_identity(
        requested_tag="X-9999",
        vision_tags=["R-1001"],
        registry=registry,
    )
    assert result.status == AssetIdentityStatus.UNKNOWN_ASSET


# ---------------------------------------------------------------------------
# 10. Identity-blocked graph does NOT call search_knowledge_base
# ---------------------------------------------------------------------------
def test_identity_blocked_skips_retrieval():
    with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
        state = create_initial_state(run_id="test", user_request="test", asset_tag="R-1001")
        state["image_path"] = "/fake/path.jpg"
        state["vision_tags"] = ["P-2104B"]
        state["plan"] = [{"category": "test", "document_type": "equipment_manual", "query": "test"}]
        state["asset_identity"] = {
            "status": "CONFLICT",
            "canonical_tag": "R-1001",
            "reason": "blocked",
        }
        out = retrieve_run(state)
        assert out["status"] == "RETRIEVAL_BLOCKED"
        assert mock_search.call_count == 0


# ---------------------------------------------------------------------------
# 11. Identity-blocked graph does NOT generate artifact
# ---------------------------------------------------------------------------
def test_identity_blocked_no_artifact():
    state = create_initial_state(run_id="test", user_request="test", asset_tag="R-1001")
    state["image_path"] = "/fake/path.jpg"
    state["vision_tags"] = ["P-2104B"]
    state["asset_identity"] = {
        "status": "CONFLICT",
        "canonical_tag": "R-1001",
        "reason": "blocked",
    }
    out = identity_run(state)
    assert out["status"] == "IDENTITY_BLOCKED"
    assert out["asset_identity"]["status"] == "CONFLICT"


# ---------------------------------------------------------------------------
# 12. Retrieval uses canonical tag only
# ---------------------------------------------------------------------------
def test_retrieval_uses_canonical_tag():
    with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
        mock_search.return_value = []
        state = create_initial_state(run_id="test", user_request="test", asset_tag="R-1001")
        state["plan"] = [{"category": "test", "document_type": "equipment_manual", "query": "test"}]
        state["asset_identity"] = {
            "status": "VERIFIED",
            "canonical_tag": "R-1001",
        }
        out = retrieve_run(state)
        assert out["status"] == "RETRIEVED"
        for call in mock_search.call_args_list:
            assert call.kwargs.get("asset_tag") == "R-1001"


# ---------------------------------------------------------------------------
# 13. Arbitrary foreign vision tag is NOT used as primary RAG query
# ---------------------------------------------------------------------------
def test_foreign_vision_tag_not_primary_query():
    with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
        mock_search.return_value = []
        state = create_initial_state(run_id="test", user_request="test", asset_tag="R-1001")
        state["plan"] = []
        state["vision_tags"] = ["TI-1001", "PI-1001"]
        state["asset_identity"] = {
            "status": "VERIFIED",
            "canonical_tag": "R-1001",
        }
        out = retrieve_run(state)
        for call in mock_search.call_args_list:
            assert call.kwargs.get("asset_tag") == "R-1001"


# ---------------------------------------------------------------------------
# 14. Foreign-asset retrieval hit is dropped even if retriever returns it
# ---------------------------------------------------------------------------
def test_foreign_asset_hit_dropped():
    with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
        mock_search.return_value = [
            {"text": "foreign", "source_file": "x", "document_type": "manual",
             "asset_tag": "R-9999", "data_origin": "test", "score": 0.9, "chunk_id": "c1", "section": ""}
        ]
        state = create_initial_state(run_id="test", user_request="test", asset_tag="R-1001")
        state["plan"] = [{"category": "test", "document_type": "equipment_manual", "query": "test"}]
        state["asset_identity"] = {
            "status": "VERIFIED",
            "canonical_tag": "R-1001",
        }
        out = retrieve_run(state)
        assert len(out["retrieved_chunks"]) == 0


# ---------------------------------------------------------------------------
# 15. Matching hit survives
# ---------------------------------------------------------------------------
def test_matching_hit_survives():
    with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
        mock_search.return_value = [
            {"text": "correct", "source_file": "m", "document_type": "manual",
             "asset_tag": "R-1001", "data_origin": "test", "score": 0.9, "chunk_id": "c1", "section": ""}
        ]
        state = create_initial_state(run_id="test", user_request="test", asset_tag="R-1001")
        state["plan"] = [{"category": "test", "document_type": "equipment_manual", "query": "test"}]
        state["asset_identity"] = {
            "status": "VERIFIED",
            "canonical_tag": "R-1001",
        }
        out = retrieve_run(state)
        assert len(out["retrieved_chunks"]) == 1
        assert out["retrieved_chunks"][0]["asset_tag"] == "R-1001"


# ---------------------------------------------------------------------------
# 16. Raw vision tags remain preserved for provenance
# ---------------------------------------------------------------------------
def test_raw_vision_tags_preserved():
    registry = _registry_with(Path(tempfile.mkdtemp()), ["R-1001"])
    result = resolve_asset_identity(
        requested_tag="R-1001",
        vision_tags=["R-1001", "TI-1001", "PI-1001"],
        registry=registry,
    )
    assert "R-1001" in result.vision_tags
    assert "TI-1001" in result.vision_tags
    assert "PI-1001" in result.vision_tags


# ---------------------------------------------------------------------------
# 17. Trace contains identity decision
# ---------------------------------------------------------------------------
def test_trace_contains_identity_decision():
    state = create_initial_state(run_id="test", user_request="test", asset_tag="R-1001")
    out = identity_run(state)
    assert len(out["trace"]) == 1
    entry = out["trace"][0]
    assert entry["node"] == "asset_identity"
    assert "requested_tag" in entry.get("fields", {}) or entry.get("requested_tag") == "R-1001"


# ---------------------------------------------------------------------------
# 18. No network/model call is required to resolve identity
# ---------------------------------------------------------------------------
def test_identity_no_network_call():
    registry = _registry_with(Path(tempfile.mkdtemp()), ["R-1001", "R-1002"])
    with patch("agent.identity.load_asset_registry", return_value=registry):
        result = resolve_asset_identity(requested_tag="R-1001", vision_tags=None, registry=registry)
    assert result.status == AssetIdentityStatus.VERIFIED_TEXT_ONLY


# ---------------------------------------------------------------------------
# Helper for retrieve node tests
# ---------------------------------------------------------------------------
from agent.nodes.retrieve import run as retrieve_run


# ===========================================================================
# PART B — Fail-closed retrieve-node regression tests (Phase 14A2)
# ===========================================================================

# ---------------------------------------------------------------------------
# B1. retrieve WITHOUT asset_identity: known R-1001, no vision → allowed
# ---------------------------------------------------------------------------
def test_retrieve_missing_identity_known_asset_text_only_allowed():
    with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
        mock_search.return_value = []
        state = {
            "asset_tag": "R-1001",
            "plan": [{"category": "test", "document_type": "equipment_manual", "query": "test"}],
            "vision_tags": [],
        }
        out = retrieve_run(state)
        assert out["status"] == "RETRIEVED"
        assert mock_search.call_count >= 1


# ---------------------------------------------------------------------------
# B2. retrieve WITHOUT asset_identity: unknown R-100I → blocked
# ---------------------------------------------------------------------------
def test_retrieve_missing_identity_unknown_asset_blocked():
    with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
        state = {
            "asset_tag": "R-100I",
            "plan": [{"category": "test", "document_type": "equipment_manual", "query": "test"}],
            "vision_tags": [],
        }
        out = retrieve_run(state)
        assert out["status"] == "RETRIEVAL_BLOCKED"
        assert mock_search.call_count == 0
        assert len(out["evidence"]) == 0


# ---------------------------------------------------------------------------
# B3. retrieve WITHOUT asset_identity: R-1001 requested, vision lacks R-1001 → blocked
# ---------------------------------------------------------------------------
def test_retrieve_missing_identity_vision_conflict_blocked():
    with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
        state = {
            "asset_tag": "R-1001",
            "plan": [{"category": "test", "document_type": "equipment_manual", "query": "test"}],
            "vision_tags": ["P-2104B", "XV-101"],
        }
        out = retrieve_run(state)
        assert out["status"] == "RETRIEVAL_BLOCKED"
        assert mock_search.call_count == 0
        assert len(out["evidence"]) == 0


# ---------------------------------------------------------------------------
# B4. malformed asset_identity dict → must NOT be trusted blindly
# ---------------------------------------------------------------------------
def test_retrieve_malformed_identity_rejected():
    with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
        state = {
            "asset_tag": "R-1001",
            "plan": [{"category": "test", "document_type": "equipment_manual", "query": "test"}],
            "asset_identity": {"foo": "bar"},
        }
        out = retrieve_run(state)
        assert out["status"] == "RETRIEVED"
        assert mock_search.call_count >= 1


# ---------------------------------------------------------------------------
# B5. manually supplied asset_identity with invalid/unrecognized status
#     → must NOT be trusted blindly → re-resolve and proceed with R-1001
# ---------------------------------------------------------------------------
def test_retrieve_invalid_identity_status_rejected_and_re_resolved():
    with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
        mock_search.return_value = []
        state = {
            "asset_tag": "R-1001",
            "plan": [{"category": "test", "document_type": "equipment_manual", "query": "test"}],
            "asset_identity": {
                "status": "INVALID_STATUS",
                "canonical_tag": "R-1001",
                "reason": "forged",
            },
        }
        out = retrieve_run(state)
        assert out["status"] == "RETRIEVED"
        assert mock_search.call_count >= 1
        for call in mock_search.call_args_list:
            assert call.kwargs.get("asset_tag") == "R-1001"


# ---------------------------------------------------------------------------
# B6. manually supplied VERIFIED identity with canonical_tag NOT in registry
#     → forged canonical_tag must be ignored, re-resolve with requested asset
# ---------------------------------------------------------------------------
def test_retrieve_forged_verified_identity_canonical_not_in_registry_rejected():
    with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
        mock_search.return_value = []
        state = {
            "asset_tag": "R-1001",
            "plan": [{"category": "test", "document_type": "equipment_manual", "query": "test"}],
            "asset_identity": {
                "status": "VERIFIED",
                "canonical_tag": "R-9999",
                "reason": "forged",
            },
        }
        out = retrieve_run(state)
        assert out["status"] == "RETRIEVED"
        assert mock_search.call_count >= 1
        for call in mock_search.call_args_list:
            assert call.kwargs.get("asset_tag") == "R-1001"
        assert len(out["evidence"]) == 0
