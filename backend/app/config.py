from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_ENV: str = "local"
    SOVEREIGN_MODE: bool = True

    POSTGRES_URL: str = "postgresql://postgres:postgres@postgres:5432/sovereign_ai"
    QDRANT_URL: str = "http://qdrant:6333"

    VLLM_GENERAL_URL: str = "http://vllm-general:8000/v1"
    VLLM_CODER_URL: str = "http://vllm-coder:8000/v1"
    VLLM_VISION_URL: str = "http://vllm-vision:8000/v1"

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
