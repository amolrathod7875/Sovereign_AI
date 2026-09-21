"""Phase 3 - Local hybrid RAG configuration (Sovereign AI).

All paths are computed from the repo root so the package works when run as a module
from the `backend/` directory. No external services are contacted.
"""
import os
from pathlib import Path

# ---- force fully-offline model loading (zero network) ----
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("SENTENCE_TRANSFORMERS_OFFLINE", "1")

REPO_ROOT = Path(__file__).resolve().parents[2]          # .../Sovereign_AI
SYNTHETIC_DIR = REPO_ROOT / "data" / "synthetic"
RAG_DIR = REPO_ROOT / "data" / "rag"
QDRANT_PATH = RAG_DIR / "qdrant_db"                     # local embedded Qdrant (RocksDB)
BM25_DIR = RAG_DIR / "bm25"

# Embedding model: explicit LOCAL filesystem path under the repository.
# The default resolves to models/embeddings/all-MiniLM-L6-v2 relative to the repo
# root so the package works from any working directory. Override via the
# EMBEDDING_MODEL env var ONLY with a different local filesystem path.
# Do NOT set this to a HuggingFace repo ID — the embedder enforces
# local_files_only=True and will fail honestly if the directory is absent.
EMBEDDING_MODEL_PATH = (REPO_ROOT / "models" / "embeddings" / "all-MiniLM-L6-v2")
EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL", str(EMBEDDING_MODEL_PATH)
)

# all-MiniLM-L6-v2 produces 384-dim sentence embeddings (normalised).
# This is the canonical dimension; Qdrant collection `sovereign_knowledge` was
# created with vectors_config size=384. Mismatches trigger a controlled error.
EMBEDDING_DIM = 384

# Dedicated Sovereign AI knowledge collection (local Qdrant).
COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "sovereign_knowledge")

# Hybrid fusion weights (configurable).
SEMANTIC_WEIGHT = float(os.environ.get("SEMANTIC_WEIGHT", "0.7"))
BM25_WEIGHT = float(os.environ.get("BM25_WEIGHT", "0.3"))

# Chunking behaviour
MAX_CHUNK_CHARS = int(os.environ.get("MAX_CHUNK_CHARS", "1200"))
MIN_CHUNK_CHARS = int(os.environ.get("MIN_CHUNK_CHARS", "80"))
