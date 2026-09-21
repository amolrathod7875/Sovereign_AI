"""Phase 12.2 — Fully Offline RAG / Local Embedding Model Tests.

Verifies that the RAG embedding/retrieval path is deterministic and explicitly
local, with honest controlled failure when the embedding model is absent.

Run from backend/:
    PYTHONPATH=backend python -m pytest tests/test_phase12_2_offline_rag.py -v
"""
import gc
import math
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Force fully-offline mode before any RAG / transformers import.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("SENTENCE_TRANSFORMERS_OFFLINE", "1")

REPO = Path(__file__).resolve().parents[2]          # .../Sovereign_AI
BACKEND_DIR = Path(__file__).resolve().parents[1]    # .../backend
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from rag import config
from rag.models.embeddings import (
    LocalEmbedder,
    EmbeddingModelUnavailable,
    EXPECTED_EMBEDDING_DIM,
)
from rag.retrieval.hybrid import HybridRetriever
from rag.indexing.qdrant_store import QdrantStore
from rag.indexing.bm25_store import BM25Store
from agent.tools.search_kb import search_knowledge_base
from agent.security.netguard import NetworkGuard


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_retriever():
    """Reset the HybridRetriever singleton between tests."""
    import rag.retrieval.hybrid as hybrid_mod
    hybrid_mod._RETRIEVER = None
    import agent.tools.search_kb as skb
    skb._RETRIEVER = None
    yield
    hybrid_mod._RETRIEVER = None
    skb._RETRIEVER = None
    gc.collect()  # release QdrantStore file handles before the next test opens the DB


# ---------------------------------------------------------------------------
# 1. Local embedding model path resolves correctly
# ---------------------------------------------------------------------------
def test_embedding_model_path_resolves():
    path = config.EMBEDDING_MODEL_PATH
    assert isinstance(path, Path), f"expected Path, got {type(path)}"
    assert path.is_absolute(), "EMBEDDING_MODEL_PATH must be absolute"
    expected = config.REPO_ROOT / "models" / "embeddings" / "all-MiniLM-L6-v2"
    assert path == expected, f"expected {expected}, got {path}"
    assert str(config.EMBEDDING_MODEL) == str(path), "EMBEDDING_MODEL must match the local path"


# ---------------------------------------------------------------------------
# 2. Missing embedding directory -> controlled failure
# ---------------------------------------------------------------------------
def test_missing_embedding_dir_controlled_failure(tmp_path):
    missing = tmp_path / "does_not_exist"
    with pytest.raises(EmbeddingModelUnavailable) as exc_info:
        LocalEmbedder(str(missing))
    msg = str(exc_info.value)
    assert "unavailable" in msg.lower()
    assert "provision" in msg.lower() or "model" in msg.lower()
    assert "does_not_exist" in msg or str(missing) in msg


# ---------------------------------------------------------------------------
# 3. Local-only loading does not attempt network
# ---------------------------------------------------------------------------
def test_local_only_no_network(tmp_path):
    model_dir = tmp_path / "fake_model"
    model_dir.mkdir()
    (model_dir / "modules.json").write_text("{}")

    with NetworkGuard() as guard:
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_instance = MagicMock()
            mock_instance.get_sentence_embedding_dimension.return_value = EXPECTED_EMBEDDING_DIM
            mock_st.return_value = mock_instance

            embedder = LocalEmbedder(str(model_dir))

            assert embedder.dim == EXPECTED_EMBEDDING_DIM

            call_args, call_kwargs = mock_st.call_args
            assert call_kwargs.get("local_files_only") is True, \
                "SentenceTransformer must be called with local_files_only=True"

    assert guard.external_calls == 0, f"network calls detected: {guard.blocked}"


# ---------------------------------------------------------------------------
# 4. No Hugging Face Hub fallback
# ---------------------------------------------------------------------------
def test_no_hf_hub_fallback():
    # The default config must be a local filesystem path, not a HF repo ID.
    assert config.EMBEDDING_MODEL == str(config.EMBEDDING_MODEL_PATH)

    # Even when an embedder is constructed, local_files_only=True is enforced.
    tmp = Path(os.environ.get("TEMP", "/tmp")) / "phase12_2_stub"
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "modules.json").write_text("{}")
    try:
        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_inst = MagicMock()
            mock_inst.get_sentence_embedding_dimension.return_value = EXPECTED_EMBEDDING_DIM
            mock_st.return_value = mock_inst
            LocalEmbedder(str(tmp))
            assert mock_st.call_args.kwargs.get("local_files_only") is True
    finally:
        (tmp / "modules.json").unlink(missing_ok=True)
        tmp.rmdir()


# ---------------------------------------------------------------------------
# 5. Embedding output dimension validated
# ---------------------------------------------------------------------------
def test_embedding_dimension_validated():
    embedder = LocalEmbedder.__new__(LocalEmbedder)
    embedder._dim = EXPECTED_EMBEDDING_DIM
    embedder._model = MagicMock()
    good_vec = [0.1] * EXPECTED_EMBEDDING_DIM
    embedder._model.encode.return_value = [good_vec]

    result = embedder.embed("test query")
    assert len(result) == 1
    assert len(result[0]) == EXPECTED_EMBEDDING_DIM
    assert all(isinstance(x, float) for x in result[0])


# ---------------------------------------------------------------------------
# 6. Malformed embedding output rejected
# ---------------------------------------------------------------------------
def test_malformed_embedding_rejected():
    embedder = LocalEmbedder.__new__(LocalEmbedder)
    embedder._dim = EXPECTED_EMBEDDING_DIM

    # NaN values
    embedder._model = MagicMock()
    embedder._model.encode.return_value = [[float("nan")] * EXPECTED_EMBEDDING_DIM]
    with pytest.raises(ValueError, match="NaN or Inf"):
        embedder.embed("query with NaN")

    # Inf values
    embedder._model.encode.return_value = [[float("inf")] * EXPECTED_EMBEDDING_DIM]
    with pytest.raises(ValueError, match="NaN or Inf"):
        embedder.embed("query with Inf")

    # Wrong dimension (too short)
    embedder._model.encode.return_value = [[0.1] * 128]
    with pytest.raises(ValueError, match="dimension"):
        embedder.embed("query wrong dim")

    # Wrong dimension (too long)
    embedder._model.encode.return_value = [[0.1] * (EXPECTED_EMBEDDING_DIM + 1)]
    with pytest.raises(ValueError, match="dimension"):
        embedder.embed("query wrong dim 2")


# ---------------------------------------------------------------------------
# 7. Qdrant dimension compatibility checked
# ---------------------------------------------------------------------------
def test_qdrant_dimension_compatible():
    """When the embedder dimension matches the Qdrant collection, no error."""
    retriever = HybridRetriever.__new__(HybridRetriever)
    mock_embedder = MagicMock()
    mock_embedder.dim = EXPECTED_EMBEDDING_DIM
    retriever.embedder = mock_embedder
    retriever._vector_available = True
    retriever._dim_checked = False
    retriever.qstore = QdrantStore()
    retriever.bm = BM25Store()

    assert retriever._check_qdrant_dim() is True


def test_qdrant_dimension_mismatch_detected():
    """When the embedder dimension differs from the stored collection, error."""
    retriever = HybridRetriever.__new__(HybridRetriever)
    mock_embedder = MagicMock()
    mock_embedder.dim = 768  # wrong
    retriever.embedder = mock_embedder
    retriever._vector_available = True
    retriever._dim_checked = False
    retriever.qstore = QdrantStore()
    retriever.bm = BM25Store()

    with pytest.raises(EmbeddingModelUnavailable, match="does not match"):
        retriever._check_qdrant_dim()


# ---------------------------------------------------------------------------
# 8. Existing BM25 path remains intact
# ---------------------------------------------------------------------------
def test_bm25_path_intact():
    bm = BM25Store()
    results = bm.search("R-1001 temperature threshold breach", top_k=5, asset_tag="R-1001")
    assert len(results) >= 1, "BM25 index should return results without an embedding model"
    for r in results:
        assert "chunk_id" in r
        assert "text" in r
        assert "metadata" in r
        assert r["metadata"]["asset_tag"] == "R-1001"


# ---------------------------------------------------------------------------
# 9. Hybrid retrieval works when local embedding model is available
# ---------------------------------------------------------------------------
def test_hybrid_retrieval_with_mock_embedder():
    """When a valid embedder is injected, full hybrid retrieval (semantic + BM25)
    operates and every result is tagged retrieval_mode='hybrid'."""
    retriever = HybridRetriever.__new__(HybridRetriever)
    mock_embedder = MagicMock()
    mock_embedder.dim = EXPECTED_EMBEDDING_DIM
    mock_embedder.embed.return_value = [[0.1] * EXPECTED_EMBEDDING_DIM]
    retriever.embedder = mock_embedder
    retriever.qstore = QdrantStore()
    retriever.bm = BM25Store()
    retriever._vector_available = True
    retriever._dim_checked = True  # skip compatibility check for this unit test

    results = retriever.retrieve(
        "R-1001 maintenance SOP", asset_tag="R-1001", top_k=6
    )
    assert len(results) >= 1, "hybrid retrieval should return results"
    assert all(r.get("retrieval_mode") == "hybrid" for r in results), \
        "all results must be tagged as hybrid mode"


# ---------------------------------------------------------------------------
# 10. Retrieval failure is honest when vector model unavailable
# ---------------------------------------------------------------------------
def test_retrieval_honest_in_degraded_mode():
    """When LocalEmbedder raises EmbeddingModelUnavailable, the retriever falls
    back to BM25-only and every result is tagged ``retrieval_mode='bm25_only'``."""
    with patch("rag.retrieval.hybrid.LocalEmbedder",
               side_effect=EmbeddingModelUnavailable("degraded mode test")):
        retriever = HybridRetriever()
    assert retriever._vector_available is False
    assert retriever.embedder is None

    results = retriever.retrieve("R-1001 maintenance", asset_tag="R-1001", top_k=6)
    assert len(results) >= 1, "BM25-only fallback should still return lexical results"
    assert all(r.get("retrieval_mode") == "bm25_only" for r in results), \
        "degraded results must be labelled bm25_only"


def test_embedder_absent_raises_controlled_error(tmp_path):
    """Direct LocalEmbedder construction with a guaranteed nonexistent path
    must raise EmbeddingModelUnavailable, not a generic or network error."""
    missing = tmp_path / "nonexistent_model_dir"
    with pytest.raises(EmbeddingModelUnavailable):
        LocalEmbedder(str(missing))


# ---------------------------------------------------------------------------
# 11. Agent retrieval propagates controlled failure / degraded state
# ---------------------------------------------------------------------------
def test_agent_search_kb_propagates_degraded():
    """search_knowledge_base must surface retrieval_mode to the agent when the
    embedder is unavailable (mocked to raise)."""
    with patch("rag.retrieval.hybrid.LocalEmbedder",
               side_effect=EmbeddingModelUnavailable("degraded mode test")):
        hits = search_knowledge_base(
            "R-1001 maintenance requirements", asset_tag="R-1001", top_k=5
        )
    assert len(hits) >= 1, "BM25-only retrieval should return results"
    for h in hits:
        assert h.get("retrieval_mode") == "bm25_only"
        assert h.get("text"), "results must contain real text, not fabricated placeholders"


# ---------------------------------------------------------------------------
# 12. Vision-grounded RAG does not fabricate evidence when retrieval fails
# ---------------------------------------------------------------------------
def test_vision_rag_no_fabrication_on_retrieval_failure():
    """When search_knowledge_base raises during vision-grounded retrieval,
    the retrieve node must record the error and produce NO evidence."""
    from agent.nodes.retrieve import run as retrieve_run

    with patch("agent.nodes.retrieve.search_knowledge_base",
               side_effect=Exception("embedding model unavailable")):
        state = {
            "asset_tag": "R-1001",
            "plan": [
                {"category": "maintenance", "document_type": "test_document",
                 "query": "what are the maintenance steps"},
            ],
            "vision_tags": ["R-1001"],
        }
        result = retrieve_run(state)

    assert len(result["evidence"]) == 0, "no evidence must be fabricated when retrieval fails"
    assert len(result["errors"]) > 0, "retrieval errors must be recorded"
    error_text = " ".join(result["errors"])
    assert "model unavailable" in error_text or "retrieval failed" in error_text.lower()


def test_vision_rag_no_fabrication_on_empty_results():
    """When search_knowledge_base returns empty (no hits), no evidence is
    fabricated and no errors are raised (empty is a valid result, not a failure)."""
    from agent.nodes.retrieve import run as retrieve_run

    with patch("agent.nodes.retrieve.search_knowledge_base", return_value=[]):
        state = {
            "asset_tag": "R-1001",
            "plan": [
                {"category": "inspection", "document_type": "test_document",
                 "query": "what abnormal conditions"},
            ],
            "vision_tags": ["R-1001"],
        }
        result = retrieve_run(state)

    assert len(result["evidence"]) == 0, "no evidence when retrieval returns nothing"
    assert len(result["retrieved_chunks"]) == 0


# ---------------------------------------------------------------------------
# Sovereignty: no network during offline embedder construction
# ---------------------------------------------------------------------------
def test_sovereignty_no_network_on_absent_model(tmp_path):
    """Constructing the embedder with a nonexistent model path must not attempt
    any network connection — it must fail locally before any I/O."""
    missing = tmp_path / "nonexistent_model_dir"
    with NetworkGuard() as guard:
        with pytest.raises(EmbeddingModelUnavailable):
            LocalEmbedder(str(missing))
    assert guard.external_calls == 0, \
        f"external network calls detected during offline embedder init: {guard.blocked}"


# ---------------------------------------------------------------------------
# 13. Real local embedding model (provisioned)
# ---------------------------------------------------------------------------
def test_real_local_embedding_model():
    """Verify the production model directory exists and loads correctly,
    produces 384-dim finite embeddings, and makes zero network calls."""
    assert config.EMBEDDING_MODEL_PATH.is_dir(), \
        f"Provision the embedding model at {config.EMBEDDING_MODEL_PATH}"

    with NetworkGuard() as guard:
        embedder = LocalEmbedder(config.EMBEDDING_MODEL)
    assert embedder.dim == EXPECTED_EMBEDDING_DIM
    assert guard.external_calls == 0, \
        f"unexpected network calls during embedder init: {guard.blocked}"

    query = "R-1001 maintenance requirements"
    with NetworkGuard() as guard:
        vecs = embedder.embed(query)
    assert len(vecs) == 1
    assert len(vecs[0]) == 384
    assert all(math.isfinite(x) for x in vecs[0]), \
        "embedding must be fully finite (no NaN/Inf)"
    assert guard.external_calls == 0, \
        f"unexpected network calls during embedding: {guard.blocked}"
