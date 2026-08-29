"""Phase 4 — Sovereign AI Agent package configuration.

Paths are derived from the repository root so the package works when imported
from the ``backend/`` directory (where the ``rag`` package also lives).
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../Sovereign_AI
BACKEND_DIR = Path(__file__).resolve().parents[1]  # .../Sovereign_AI/backend

SYNTHETIC_DIR = REPO_ROOT / "data" / "synthetic"
ASSETS_DIR = SYNTHETIC_DIR / "assets" / "R-1001"

# New agent artifacts are written here (NEVER the original synthetic approval note).
OUTPUT_DIR = REPO_ROOT / "data" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Local, fully-offline embeddings/Qdrant/BM25 are provided by the Phase 3 rag package.
RAG_COLLECTION = "sovereign_knowledge"

# Error-recovery: how many times verify_output may request regeneration.
MAX_GENERATION_RETRIES = 2

# Author used in generated artifacts.
AGENT_AUTHOR = "Sovereign AI — Maintenance Agent"
