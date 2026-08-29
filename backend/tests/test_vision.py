"""Phase 5B — Tests for the local vision tool and its agent integration.

These tests exercise the SINGLE authoritative vision tool (``agent.tools.vision``)
and the LangGraph maintenance agent. All vision inference is local (llama.cpp on
127.0.0.1:8003) and the network guard enforces zero external calls.

Run from ``backend/``:
    PYTHONPATH=. python -m pytest tests/test_vision.py -v
"""
import os
import socket
from pathlib import Path

import httpx
import pytest

from agent.tools.vision import (
    analyze_image,
    analyze_pid,
    extract_equipment_tags,
    validate_path,
    _assert_local_endpoint,
    _structure_result,
    _status_of,
)
from agent.security.netguard import no_network
from agent.run import run_agent_task

REPO = Path(__file__).resolve().parents[2]
PID = REPO / "PID_Dataset" / "0__raw_data" / "sheets" / "test"
IMG = str(PID / "158.jpg")
VISION_ENDPOINT = "http://localhost:8003/v1"

CANONICAL_KEYS = {
    "file", "analysis_type", "description", "findings", "entities",
    "uncertain_items", "confidence", "model", "data_origin",
    "timestamp", "source_file",
}


@pytest.fixture
def _offline():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _server_up() -> bool:
    try:
        with httpx.Client(timeout=2.0) as c:
            r = c.get(f"{VISION_ENDPOINT}/models")
            return r.status_code == 200
    except Exception:
        return False


requires_server = pytest.mark.skipif(not _server_up(), reason="local vision server not running on :8003")


# 1. Vision server connectivity ------------------------------------------------
def test_vision_server_connectivity():
    assert _server_up(), "expected the local llama.cpp vision server on 127.0.0.1:8003"
    # The tool must refuse any non-local endpoint (sovereignty).
    with pytest.raises(ConnectionError):
        _assert_local_endpoint("http://1.2.3.4/v1")
    # Loopback / private hosts are allowed.
    _assert_local_endpoint("http://localhost:8003/v1")
    _assert_local_endpoint("http://127.0.0.1:8003/v1")


# 2. Image analysis ------------------------------------------------------------
@requires_server
def test_image_analysis_returns_canonical_schema(_offline):
    res = analyze_image(IMG, analysis_type="general",
                        prompt="Describe this engineering drawing briefly.")
    assert CANONICAL_KEYS.issubset(res.keys()), res.keys()
    assert res["data_origin"] == "local"
    assert res["model"] == "Qwen2.5-VL-3B-Instruct"
    assert isinstance(res["findings"], list)
    assert isinstance(res["entities"], list)
    assert isinstance(res["uncertain_items"], list)
    assert 0.0 <= res["confidence"] <= 1.0


# 3. P&ID analysis -------------------------------------------------------------
@requires_server
def test_pid_analysis_returns_structured_evidence(_offline):
    res = analyze_pid(IMG, prompt="Identify equipment, tags and relationships.")
    assert res["analysis_type"] == "pid"
    assert CANONICAL_KEYS.issubset(res.keys())
    # P&ID mode enriches entities with equipment classes.
    types = {e.get("type") for e in res["entities"]}
    assert any(t in types for t in ("equipment_tag", "pumps", "vessels", "valves", "instruments"))


# 4. Invalid image handling ----------------------------------------------------
def test_invalid_image_type_rejected():
    bad = REPO / "reports" / "_not_an_image.txt"
    bad.write_text("not an image")
    try:
        with pytest.raises(ValueError):
            validate_path(str(bad))
    finally:
        bad.unlink(missing_ok=True)


# 5. Missing file handling -----------------------------------------------------
def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        validate_path(str(PID / "does_not_exist.jpg"))


# 6. Uncertainty preservation --------------------------------------------------
def test_uncertainty_is_preserved_in_schema():
    # The structured schema MUST always carry an uncertain_items list, and the
    # status classifier must flag uncertain / not_visible / conflict text.
    assert _status_of("this element is uncertain") == "uncertain"
    assert _status_of("label not visible") == "not_visible"
    assert _status_of("values conflict") == "conflict"
    raw = {
        "plant_system": "Reactor system (uncertain)",
        "equipment": ["Reactor R-1001 (verified)"],
        "equipment_tags": ["R-1001"],
        "uncertain": ["valve tag unreadable (uncertain)"],
    }
    structured = _structure_result("pid", raw, "158.jpg", "p")
    assert "uncertain" in structured["uncertain_items"][0].lower()
    assert any("R-1001" in str(e.get("name", "")) for e in structured["entities"])


# 7. Network isolation ---------------------------------------------------------
@requires_server
def test_vision_inference_stays_local(_offline):
    with no_network() as guard:
        res = analyze_image(IMG, analysis_type="general",
                            prompt="Briefly describe this drawing.")
    # The only socket used is loopback; no external connection may be recorded.
    assert guard.external_calls == 0, guard.blocked
    assert res["data_origin"] == "local"


# 8. Agent -> vision integration ----------------------------------------------
@requires_server
def test_agent_invokes_vision_tool(_offline):
    res = run_agent_task(
        "Inspect P&ID 158.jpg and summarize the visible equipment.",
        asset_tag="R-1001",
        run_id="t_vision_integration",
        artifact_filename="R-1001_test_vision.docx",
        image_path=IMG,
        analysis_type="pid",
    )
    assert res["vision_evidence"], "agent must call the vision tool"
    assert res["external_calls"] == 0


# 9. Vision -> RAG integration -------------------------------------------------
@requires_server
def test_vision_tags_drive_rag_retrieval(_offline):
    res = run_agent_task(
        "Inspect P&ID 158.jpg and connect any identified R-1001 information to the "
        "local knowledge base.",
        asset_tag="R-1001",
        run_id="t_vision_rag",
        artifact_filename="R-1001_test_vision_rag.docx",
        image_path=IMG,
        analysis_type="pid",
    )
    # The VLM-extracted tag must be forwarded to the retriever.
    assert res["vision_tags"], "vision tool must extract equipment tags"
    assert res["evidence"], "vision-grounded RAG retrieval must return evidence"


# 10. End-to-end multimodal task ------------------------------------------------
@requires_server
def test_end_to_end_multimodal_task(_offline):
    res = run_agent_task(
        "Inspect P&ID 158.jpg and connect any identified R-1001 information to the "
        "local knowledge base. Explain the relevant R-1001 context using only "
        "retrieved local evidence.",
        asset_tag="R-1001",
        run_id="t_e2e_multimodal",
        artifact_filename="R-1001_test_e2e.docx",
        image_path=IMG,
        analysis_type="pid",
    )
    assert res["status"] == "VERIFIED"
    assert res["external_calls"] == 0
    assert res["vision_evidence"]
    assert res["artifacts"]
    assert os.path.exists(res["artifacts"][0])
