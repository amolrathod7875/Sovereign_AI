"""Phase 5C-2 — Unified local model router tests.

Covers the required matrix:
  1. Coding task -> Qwen Coder
  2. Vision task -> Qwen-VL
  3. Document/knowledge task -> general model
  4. RAG task -> RAG + appropriate model
  5. Multimodal task -> Qwen-VL + RAG + reasoning
  6. Local-only enforcement
  7. Unknown model rejected
  8. Unavailable model handled (selection independent of online status)
  9. Model registry lookup
 10. Router confidence
 11. Routing decision schema
 12. Agent -> router integration
 13. Router -> model integration (execute_routing)
 14. Existing Qwen Coder path resolves
 15. Existing Qwen-VL path resolves (server-dependent)
 16. Existing RAG retrieval works (local, no model server needed)
"""
import os

import pytest

from app.models.registry import (
    get_model, get_models_with_capability, get_local_models,
    is_local_endpoint, validate_local_endpoint, register_model, unregister_model,
)
from app.models.router import route, RoutingRequest, NoLocalModelAvailable
from app.schemas import RoutingDecision

REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
PID = REPO / "PID_Dataset" / "0__raw_data" / "sheets" / "test"
IMG = str(PID / "158.jpg")
VISION_ENDPOINT = "http://localhost:8003/v1"


@pytest.fixture(autouse=True)
def _offline():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _server_up() -> bool:
    try:
        import httpx
        with httpx.Client(timeout=2.0) as c:
            return c.get(f"{VISION_ENDPOINT}/models").status_code == 200
    except Exception:
        return False


requires_server = pytest.mark.skipif(
    not _server_up(), reason="local vision server not running on :8003"
)


# 1. Coding -> Coder ---------------------------------------------------------
def test_coding_routes_to_coder():
    d = route(RoutingRequest(
        task="Write a Python function that calculates Reynolds number."))
    assert d.selected_model == "qwen-coder"
    assert "qwen-coder" in d.models_required
    assert d.requires_tools is True


# 2. Vision -> VL ------------------------------------------------------------
def test_vision_routes_to_vision():
    d = route(RoutingRequest(
        task="Identify the major equipment and equipment tags visible in this P&ID image."))
    assert d.selected_model == "vision"
    assert "vision" in d.models_required
    assert any("vision" in c.lower() for c in d.capabilities)


# 3. Document/knowledge -> general -------------------------------------------
def test_document_task_routes_to_general():
    d = route(RoutingRequest(
        task="Summarize the maintenance SOP for R-1001."))
    assert d.selected_model == "general"
    assert "general" in d.models_required


# 4. RAG task -> RAG + general ----------------------------------------------
def test_rag_task_requires_rag():
    d = route(RoutingRequest(
        task="Explain the maintenance requirements for R-1001 using the local knowledge base."))
    assert d.requires_rag is True
    assert "general" in d.models_required
    assert d.task_type == "RAG_QA"


# 5. Multimodal -> VL + general + RAG ---------------------------------------
def test_multimodal_uses_multiple_models():
    d = route(RoutingRequest(
        task="Inspect P&ID 158.jpg, identify R-1001, and explain the relevant "
             "maintenance information using the local knowledge base.",
        image_path=IMG))
    assert "vision" in d.models_required
    assert "general" in d.models_required
    assert d.requires_rag is True
    assert len(d.models_required) >= 2


# 6. Local-only enforcement --------------------------------------------------
def test_local_only_enforcement():
    assert is_local_endpoint("http://localhost:8002/v1") is True
    assert is_local_endpoint("http://127.0.0.1:8003/v1") is True
    assert is_local_endpoint("http://api.openai.com/v1") is False
    # A model flagged local=True but pointing at a public endpoint must be rejected.
    # Remove the real coder so 'evil' is the ONLY code-capable model; routing it
    # must raise (sovereignty guard), never call the external endpoint.
    saved_coder = get_model("qwen-coder")
    unregister_model("qwen-coder")
    register_model("evil", {
        "id": "evil", "name": "evil", "endpoint": "http://1.2.3.4/v1",
        "capabilities": ["code_generation"], "modalities": ["text"],
        "local": True, "model_type": "coder",
    })
    try:
        with pytest.raises(Exception):
            route(RoutingRequest(task="write code", requires_code=True))
    finally:
        unregister_model("evil")
        register_model("qwen-coder", saved_coder)


# 7. Unknown model rejected --------------------------------------------------
def test_unknown_model_rejected():
    saved = get_model("qwen-coder")
    unregister_model("qwen-coder")
    try:
        with pytest.raises(NoLocalModelAvailable):
            route(RoutingRequest(task="write a python function", requires_code=True))
    finally:
        register_model("qwen-coder", saved)


# 8. Unavailable (offline) model still selected by capability ---------------
def test_unavailable_model_handled():
    m = get_model("qwen-coder")
    old = m["status"]
    m["status"] = "offline"
    try:
        d = route(RoutingRequest(task="write a python function", requires_code=True))
        # selection is by capability + local, not by online status
        assert d.selected_model == "qwen-coder"
    finally:
        m["status"] = old


# 9. Registry lookup ---------------------------------------------------------
def test_registry_lookup():
    assert get_model("vision")["name"] == "Qwen-VL-3B"
    caps = get_models_with_capability("vision")
    assert any(mid == "vision" for mid, _ in caps)
    assert all(m.get("local") for _, m in get_local_models())


# 10. Confidence -------------------------------------------------------------
def test_router_confidence():
    for t in [
        "write a python script",
        "identify equipment in this image",
        "explain R-1001 maintenance from the knowledge base",
    ]:
        d = route(RoutingRequest(task=t))
        assert 0.0 <= d.confidence <= 1.0
        assert d.confidence >= 0.5


# 11. Routing decision schema -----------------------------------------------
def test_routing_decision_schema():
    d = route(RoutingRequest(task="write a python function", requires_code=True))
    assert isinstance(d, RoutingDecision)
    assert d.local_only is True
    assert d.all_local is True
    assert d.external_calls == 0
    dumped = d.model_dump()
    assert set(["task_type", "selected_model", "models_required", "reason"]).issubset(dumped)


# 12. Agent -> router integration -------------------------------------------
def test_agent_includes_routing():
    from agent.run import run_agent_task
    res = run_agent_task(
        "Explain the maintenance requirements for R-1001 using the local knowledge base.",
        asset_tag="R-1001",
    )
    assert "routing" in res
    assert res["routing"]["selected_model"] == "general"
    assert res["external_calls"] == 0


# 13. Router -> model integration (vision execution) ------------------------
@requires_server
def test_router_executes_vision():
    from app.models.router import execute_routing
    d = route(RoutingRequest(
        task="Identify the major equipment in this P&ID.", image_path=IMG))
    out = execute_routing(d, task="Identify the major equipment in this P&ID.",
                          image_path=IMG)
    assert "vision" in out["models_used"]
    assert out["external_calls"] == 0
    assert out["outputs"]["vision_tags"] or out["outputs"]["vision"].get("findings")


# 14. Existing Coder workflow path resolves ---------------------------------
def test_coder_workflow_path_resolves():
    d = route(RoutingRequest(task="generate python code", requires_code=True))
    assert d.selected_model == "qwen-coder"
    # The existing coder agent uses the same id/endpoint the router selects.
    from agent.coder.config import CODER_MODEL_ID
    assert CODER_MODEL_ID == "qwen-coder"


# 15. Existing VL workflow path resolves (server-dependent) -----------------
@requires_server
def test_vision_workflow_path_resolves():
    from agent.tools.vision import analyze_image
    res = analyze_image(IMG, prompt="List equipment tags.", analysis_type="pid")
    assert res["data_origin"] == "local"
    assert res["model"]


# 16. Existing RAG retrieval works (local) ----------------------------------
def test_rag_retrieval_works():
    from agent.tools.search_kb import search_knowledge_base
    hits = search_knowledge_base("R-1001 maintenance", asset_tag="R-1001", top_k=4)
    assert len(hits) >= 1
    assert all(h.get("document_type") for h in hits)
