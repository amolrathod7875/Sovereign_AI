"""Phase 4 — Sovereign AI Agent package configuration.

Paths are derived from the repository root so the package works when imported
from the ``backend/`` directory (where the ``rag`` package also lives).
"""
import os
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

# ---------------------------------------------------------------------------
# Local Qwen2.5-VL vision model (served by llama.cpp / llama-server on a
# dedicated local port, OpenAI-compatible /v1 interface).
#
# Inference is ALWAYS local. The endpoint MUST be a loopback / private address;
# the vision tool refuses to connect to anything else and the agent run is
# wrapped in a NetworkGuard that blocks external sockets.
# ---------------------------------------------------------------------------
VISION_ENDPOINT = os.environ.get("VISION_ENDPOINT", "http://localhost:8003/v1")
VISION_MODEL_NAME = os.environ.get("VISION_MODEL_NAME", "Qwen2.5-VL-3B-Instruct")

# Per-request timeout (seconds) for a single vision call.
VISION_TIMEOUT = float(os.environ.get("VISION_TIMEOUT", "300"))

# Directories the vision tool is permitted to read from. Anything outside this
# allow-list is rejected (prevents arbitrary filesystem access / exfiltration of
# .env, credentials, SSH keys, system files, unrelated directories).
APPROVED_VISION_DIRS = [
    str(REPO_ROOT / "PID_Dataset"),
    str(REPO_ROOT / "data"),
    str(REPO_ROOT / "uploads"),
    str(REPO_ROOT / "demo-data"),
    str(REPO_ROOT / "models"),
    str(REPO_ROOT / "reports"),
    str(REPO_ROOT / "backend"),
    str(REPO_ROOT),  # allow the repo root itself (e.g. top-level datasets)
]

# File extensions the vision tool will accept.
SUPPORTED_VISION_EXT = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".pdf",
}

# For scanned-document mode: if extracted text length (chars) is below this,
# the pages are rendered and sent to the VLM instead of / in addition to text.
PDF_TEXT_MIN_CHARS = int(os.environ.get("PDF_TEXT_MIN_CHARS", "200"))

# Maximum number of PDF pages rendered and sent to the VLM (to bound latency).
PDF_MAX_PAGES = int(os.environ.get("PDF_MAX_PAGES", "10"))

# Longest-edge resolution the vision tool downscales raster images / PDF page
# renders to before sending them to the VLM. CLIP image-encoding dominates CPU
# latency and scales with pixel count, so keeping this modest makes local
# inference practical (the model still receives the whole drawing, just smaller).
VISION_MAX_EDGE = int(os.environ.get("VISION_MAX_EDGE", "768"))


def is_path_approved(path) -> bool:
    """Return True if ``path`` resolves inside an approved directory."""
    from pathlib import Path
    try:
        p = Path(path).resolve()
    except Exception:
        return False
    approved = [Path(d).resolve() for d in APPROVED_VISION_DIRS]
    return any(str(p).startswith(str(d) + os.sep) or p == d for d in approved)
