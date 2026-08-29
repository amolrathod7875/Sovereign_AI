"""Phase 5A — Sovereign AI local coding agent configuration.

Reuses the repo-root layout from ``agent.config`` and points at the existing
OpenAI-compatible Qwen Coder server (``scripts/serve_model.py``), never the cloud.
"""
import os
from pathlib import Path

from agent.config import REPO_ROOT

# Model served by scripts/serve_model.py --model-id qwen-coder --port 8002
CODER_MODEL_ID = "qwen-coder"
CODER_ENDPOINT = os.environ.get("CODER_ENDPOINT", "http://localhost:8002/v1")

# Isolation root for generated code (one subdir per run).
CODER_DIR = REPO_ROOT / "data" / "code_runs"
# Human-facing artifact location required by the spec.
CODER_ARTIFACT_DIR = REPO_ROOT / "data" / "outputs" / "coder_demo"

# Repair-loop safety bound (maximum number of FIX_CODE iterations).
CODER_MAX_ITERATIONS = 5

# Hard wall-clock limits for untrusted generated code / tests.
CODER_EXEC_TIMEOUT = 60
# Model inference wall-clock (small local model on CPU can be slow).
CODER_MODEL_TIMEOUT = 300

for _d in (CODER_DIR, CODER_ARTIFACT_DIR):
    _d.mkdir(parents=True, exist_ok=True)
