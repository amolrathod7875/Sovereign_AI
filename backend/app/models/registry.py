from typing import Dict, List, Optional
from app.config import settings

model_registry: Dict[str, Dict] = {
    "general": {
        "name": "Qwen2.5-3B-Instruct",
        "endpoint": settings.VLLM_GENERAL_URL,
        "capabilities": ["text_generation", "tool_calling", "reasoning", "summarization"],
        "context_length": 8192,
        "status": "standby",
        "vram_gb": 2.1,
        "model_type": "general",
    },
    "coder": {
        "name": "Qwen2.5-Coder-3B-Instruct",
        "endpoint": settings.VLLM_CODER_URL,
        "capabilities": ["text_generation", "code_generation", "tool_calling"],
        "context_length": 8192,
        "status": "standby",
        "vram_gb": 2.4,
        "model_type": "coder",
    },
    "vision": {
        "name": "Qwen-VL-3B",
        "endpoint": settings.VLLM_VISION_URL,
        "capabilities": ["vision", "image_analysis", "text_generation"],
        "context_length": 4096,
        "status": "offline",
        "vram_gb": 3.8,
        "model_type": "vision",
    },
    "embedding": {
        "name": "BGE-large-en-v1.5",
        "endpoint": settings.EMBEDDING_MODEL,
        "capabilities": ["embedding"],
        "context_length": 512,
        "status": "online",
        "vram_gb": 1.2,
        "model_type": "embedding",
    },
    "reranker": {
        "name": "BGE-reranker-large",
        "endpoint": settings.RERANKER_MODEL,
        "capabilities": ["reranking"],
        "context_length": 512,
        "status": "online",
        "vram_gb": 1.4,
        "model_type": "reranker",
    },
}


def register_model(model_id: str, model_config: Dict):
    model_registry[model_id] = model_config


def unregister_model(model_id: str):
    if model_id in model_registry:
        del model_registry[model_id]


def list_models() -> List[tuple]:
    return [(mid, model) for mid, model in model_registry.items()]


def get_model(model_id: str) -> Optional[Dict]:
    return model_registry.get(model_id)


def update_model_status(model_id: str, status: str):
    if model_id in model_registry:
        model_registry[model_id]["status"] = status
