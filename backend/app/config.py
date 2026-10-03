from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List, Optional

# Repository root (…/Sovereign_AI), derived from this file so local runs work from
# any working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_ENV: str = "local"
    SOVEREIGN_MODE: bool = True

    # PostgreSQL. The docker-compose deployment uses the service name "postgres".
    # For local/standalone runs (no docker) override with a real async Postgres URL,
    # e.g. postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/sovereign_ai.
    # NOTE: the app uses the async SQLAlchemy engine, so the driver MUST be async
    # (postgresql+asyncpg://). Using the sync psycopg2 driver raises at import time.
    # Use backend/.env to set the real password for the local instance.
    POSTGRES_URL: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/sovereign_ai"

    # Qdrant. The authoritative agent RAG path uses an embedded local Qdrant
    # (see backend/rag/config.py: QDRANT_PATH), so this server is only needed by
    # the /api/rag endpoints. When unreachable the backend degrades gracefully.
    QDRANT_URL: str = "http://localhost:6333"

    VLLM_GENERAL_URL: str = "http://vllm-general:8000/v1"
    VLLM_CODER_URL: str = "http://vllm-coder:8000/v1"
    VLLM_VISION_URL: str = "http://vllm-vision:8000/v1"

    # Local OpenAI-compatible Qwen Coder server (scripts/serve_model.py --port 8002).
    # Used by the local coding agent so it never leaves the machine.
    CODER_ENDPOINT: str = "http://localhost:8002/v1"

    # Production GPU configuration (validated Phases 11.4-11.8 on RTX 4050).
    # These are the recommended --n-gpu-layers / --n-ctx values for scripts/serve_model.py.
    CODER_N_GPU_LAYERS: int = 40
    CODER_N_CTX: int = 2048
    VISION_N_GPU_LAYERS: int = 99
    VISION_N_CTX: int = 2048

    EMBEDDING_MODEL: str = str(_REPO_ROOT / "models" / "embeddings" / "all-MiniLM-L6-v2")
    RERANKER_MODEL: str = "/models/reranker"

    PISTON_URL: str = "http://piston:2000"

    # Local-run defaults are repo-relative ABSOLUTE paths. The container deployment
    # overrides both with /data/... via environment (see infra/docker-compose*.yml).
    #
    # UPLOAD_DIR must live inside the repository because the authoritative vision
    # tool only reads from `agent.config.APPROVED_VISION_DIRS` (a path allow-list).
    # The previous "/data/uploads" default resolved outside that allow-list on a
    # non-container host, so an uploaded P&ID could never be analysed.
    ARTIFACT_DIR: str = str(_REPO_ROOT / "data" / "artifacts")
    UPLOAD_DIR: str = str(_REPO_ROOT / "uploads")

    # Directory the authoritative agent writes its DOCX artifacts to
    # (mirrors agent.config.OUTPUT_DIR). Read-only for the API/frontend.
    AGENT_OUTPUT_DIR: str = str(_REPO_ROOT / "data" / "outputs")

    # CORS: explicit local development origins only (Vite dev server + preview).
    # Never "*" — see Phase 6 Part 16. Override with a comma-separated env value.
    CORS_ALLOW_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:4173,http://127.0.0.1:4173,"
        "http://localhost:5173,http://127.0.0.1:5173"
    )

    # M1 local development principal (not authentication — see identity/principal.py).
    # Replace only the principal resolver in a future auth phase.
    SOVEREIGN_DEV_ORGANIZATION_ID: str = "00000000-0000-0000-0000-000000000001"
    SOVEREIGN_DEV_USER_ID: str = "00000000-0000-0000-0000-000000000002"
    SOVEREIGN_DEV_DISPLAY_NAME: str = "Local Development User"

    # M2 dynamic conversation context (Phase M2 — PostgreSQL history)
    CONVERSATION_CONTEXT_MAX_MESSAGES: int = 20
    CONVERSATION_CONTEXT_TOKEN_BUDGET: int = 500

    # M3 persistent conversation summary (Phase M3 — rolling compression)
    CONVERSATION_SUMMARY_TRIGGER_MESSAGES: int = 16
    CONVERSATION_SUMMARY_KEEP_RECENT_MESSAGES: int = 8
    CONVERSATION_SUMMARY_REFRESH_MIN_MESSAGES: int = 6
    CONVERSATION_SUMMARY_MAX_TOKENS: int = 220

    # M4 canonical long-term memory (Phase M4 — PostgreSQL durable memory)
    MEMORY_MIN_IMPORTANCE: float = 0.60
    MEMORY_MIN_CONFIDENCE: float = 0.75
    MEMORY_MAX_CANDIDATES_PER_TURN: int = 3
    MEMORY_CONTENT_MAX_LENGTH: int = 1000

    # M5 semantic memory index (Phase M5 — local embedded Qdrant index)
    MEMORY_QDRANT_PATH: str = str(_REPO_ROOT / "data" / "memory" / "qdrant_db")
    MEMORY_QDRANT_COLLECTION: str = "sovereign_memory"
    MEMORY_EMBEDDING_DIM: int = 384
    MEMORY_SEARCH_DEFAULT_TOP_K: int = 5
    MEMORY_SEARCH_CANDIDATE_MULTIPLIER: int = 4
    MEMORY_OUTBOX_BATCH_SIZE: int = 25
    MEMORY_OUTBOX_MAX_ATTEMPTS: int = 5
    MEMORY_OUTBOX_PROCESSING_TIMEOUT_SECONDS: int = 300

    MAX_FILE_MB: int = 50
    SANDBOX_TIMEOUT_SECONDS: int = 10
    MAX_OUTPUT_KB: int = 256

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = str(_REPO_ROOT / "backend" / ".env")
        case_sensitive = True


settings = Settings()
