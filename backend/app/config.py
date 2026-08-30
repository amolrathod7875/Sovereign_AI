from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_ENV: str = "local"
    SOVEREIGN_MODE: bool = True

    # PostgreSQL. The docker-compose deployment uses the service name "postgres".
    # For local/standalone runs (no docker) override with a real async Postgres URL,
    # e.g. postgresql+asyncpg://postgres:postgres@localhost:5432/sovereign_ai.
    # NOTE: the app uses the async SQLAlchemy engine, so the driver MUST be async
    # (postgresql+asyncpg://). Using the sync psycopg2 driver raises at import time.
    POSTGRES_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sovereign_ai"

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

    EMBEDDING_MODEL: str = "/models/embedding"
    RERANKER_MODEL: str = "/models/reranker"

    PISTON_URL: str = "http://piston:2000"

    ARTIFACT_DIR: str = "/data/artifacts"
    UPLOAD_DIR: str = "/data/uploads"

    MAX_FILE_MB: int = 50
    SANDBOX_TIMEOUT_SECONDS: int = 10
    MAX_OUTPUT_KB: int = 256

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
