import dataclasses
import httpx
import logging
from typing import Optional, Dict, Any
import json

from app.config import settings
from app.models.registry import update_model_status

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ModelPerformanceMetrics:
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    inference_seconds: Optional[float] = None
    tokens_per_second: Optional[float] = None


class ModelClientError(Exception):
    """Raised when the local model returns a malformed or invalid response."""
    pass


class ModelBusyError(Exception):
    """Raised when the local GPU inference capacity is busy (HTTP 429)."""
    pass


class ModelClient:
    def __init__(self, model_id: str, endpoint: str):
        self.model_id = model_id
        self.endpoint = endpoint
        self.client = httpx.AsyncClient(timeout=120.0)

    async def generate(
        self,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 120.0,
        **kwargs,
    ) -> str:
        result = await self.generate_with_metrics(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            **kwargs,
        )
        return result["content"]

    async def generate_with_metrics(
        self,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: float = 120.0,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            response = await self.client.post(
                f"{self.endpoint}/chat/completions",
                json={
                    "model": self.model_id,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    **kwargs,
                },
                timeout=timeout,
            )
            if response.status_code == 429:
                raise ModelBusyError(
                    f"Local GPU inference capacity is busy (model={self.model_id}). "
                    "Retry later."
                )
            response.raise_for_status()
            result = response.json()

            # Validate response structure for OpenAI-compatible API
            if not isinstance(result, dict):
                raise ModelClientError(f"Model {self.model_id} returned non-JSON response")

            if "choices" not in result or not isinstance(result["choices"], list) or len(result["choices"]) == 0:
                raise ModelClientError(f"Model {self.model_id} response missing or invalid 'choices' field")

            first_choice = result["choices"][0]
            if not isinstance(first_choice, dict) or "message" not in first_choice:
                raise ModelClientError(f"Model {self.model_id} response missing 'message' in choices")

            message = first_choice["message"]
            if not isinstance(message, dict) or "content" not in message:
                raise ModelClientError(f"Model {self.model_id} response missing 'content' in message")

            content = message["content"]
            usage = result.get("usage") or {}
            performance_raw = result.get("performance") or {}
            if not isinstance(performance_raw, dict):
                performance_raw = {}
            metrics = ModelPerformanceMetrics(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                inference_seconds=performance_raw.get("inference_seconds") if isinstance(performance_raw, dict) else None,
                tokens_per_second=performance_raw.get("tokens_per_second") if isinstance(performance_raw, dict) else None,
            )
            return {
                "content": content,
                "usage": {
                    "prompt_tokens": metrics.prompt_tokens,
                    "completion_tokens": metrics.completion_tokens,
                    "total_tokens": metrics.total_tokens,
                },
                "performance": dataclasses.asdict(metrics),
            }
        except Exception as e:
            logger.error(f"Model inference error for {self.model_id}: {e}")
            raise

    async def embed(self, texts: list) -> list:
        try:
            response = await self.client.post(
                f"{self.endpoint}/embeddings",
                json={"input": texts, "model": self.model_id},
            )
            response.raise_for_status()
            result = response.json()
            return [item["embedding"] for item in result["data"]]
        except Exception as e:
            logger.error(f"Embedding error for {self.model_id}: {e}")
            raise

    async def close(self):
        await self.client.aclose()


class ModelLoader:
    def __init__(self):
        self.loaded_models: Dict[str, ModelClient] = {}

    async def load_model(self, model_id: str) -> ModelClient:
        from app.models.registry import get_model

        model = get_model(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found in registry")

        if model_id not in self.loaded_models:
            client = ModelClient(model_id, model["endpoint"])
            self.loaded_models[model_id] = client
            update_model_status(model_id, "active")
            logger.info(f"Loaded model: {model_id}")

        return self.loaded_models[model_id]

    async def unload_model(self, model_id: str):
        if model_id in self.loaded_models:
            await self.loaded_models[model_id].close()
            del self.loaded_models[model_id]
            update_model_status(model_id, "standby")
            logger.info(f"Unloaded model: {model_id}")

    def get_client(self, model_id: str) -> Optional[ModelClient]:
        return self.loaded_models.get(model_id)


model_loader = ModelLoader()


async def get_model_client(model_id: str) -> ModelClient:
    return await model_loader.load_model(model_id)
