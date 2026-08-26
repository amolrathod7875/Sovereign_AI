import httpx
import logging
from typing import Optional, Dict, Any
import json

from app.config import settings
from app.models.registry import update_model_status

logger = logging.getLogger(__name__)


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
        **kwargs,
    ) -> str:
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
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
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
