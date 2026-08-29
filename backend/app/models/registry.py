"""Sovereign AI — local model registry.

Single source of truth for every model the platform may route to. Every entry is
LOCAL: weights live on this machine and are served through an OpenAI-compatible
server on a loopback / private address. No cloud model is ever registered.

Endpoints are discovered from the running configuration (environment + the
existing ``app.config`` settings). The two local servers that actually run on this
host are:

  * Qwen2.5-Coder-3B-Instruct  -> http://localhost:8002/v1  (scripts/serve_model.py)
  * Qwen2.5-VL-3B-Instruct     -> http://localhost:8003/v1  (llama.cpp / llama-server)

The ``general`` (Qwen2.5-3B-Instruct) reasoning model is registered with its
configured endpoint; if its server/weights are not present on a given host the
router still selects it by capability and the execution layer reports it
unavailable rather than falling back to an external model.

Helpers
-------
  get_model(model_id)               -> dict | None
  list_models()                     -> List[(id, dict)]
  get_local_models()                -> List[(id, dict)]   (local is True)
  get_models_with_capability(cap)   -> List[(id, dict)]   (local + capability match)
  is_local_endpoint(url)            -> bool                (loopback / private)
  validate_local_endpoint(url)      -> None | raises       (sovereignty guard)
"""
import os
import ipaddress
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.config import settings


# ---------------------------------------------------------------------------
# Local-endpoint sovereignty guard
# ---------------------------------------------------------------------------
def is_local_endpoint(url: str) -> bool:
    """Return True iff ``url`` resolves to a loopback or private (RFC1918) host.

    Public / external hosts are rejected so model inference can never leave the
    machine. Unresolvable hostnames are treated as NON-local (they would require
    DNS / external network) and therefore rejected.
    """
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1", "ip6-localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # hostname that needs DNS resolution -> not local
    return ip.is_loopback or ip.is_private


def validate_local_endpoint(url: str) -> None:
    if not is_local_endpoint(url):
        raise ConnectionError(
            f"Model endpoint '{url}' is not loopback/private. "
            f"Inference must remain local (Sovereign AI)."
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# Endpoints are taken from the running local servers discovered in the repo.
# They can be overridden by environment variables (same vars the agents use).
# Convention on this host: coder -> :8002, vision -> :8003, general -> :8001
# (all loopback; in a containerised deploy these resolve to private service names).
_CODER_ENDPOINT = os.environ.get("CODER_ENDPOINT", "http://localhost:8002/v1")
_VISION_ENDPOINT = os.environ.get("VISION_ENDPOINT", "http://localhost:8003/v1")
_GENERAL_ENDPOINT = os.environ.get("GENERAL_ENDPOINT", "http://localhost:8001/v1")

model_registry: Dict[str, Dict] = {
    "general": {
        "id": "general",
        "name": "Qwen2.5-3B-Instruct",
        "display_name": "Qwen2.5-3B-Instruct (general / reasoning)",
        "endpoint": _GENERAL_ENDPOINT,
        "capabilities": [
            "text_generation", "reasoning", "summarization",
            "rag_synthesis", "tool_calling",
        ],
        "modalities": ["text"],
        "context_length": 8192,
        "status": "standby",
        "vram_gb": 2.1,
        "model_type": "general",
        "local": True,
    },
    "qwen-coder": {
        "id": "qwen-coder",
        "name": "Qwen2.5-Coder-3B-Instruct",
        "display_name": "Qwen2.5-Coder-3B-Instruct",
        "endpoint": _CODER_ENDPOINT,
        "capabilities": [
            "text_generation", "code_generation", "code_review",
            "debugging", "tool_calling",
        ],
        "modalities": ["text"],
        "context_length": 8192,
        "status": "standby",
        "vram_gb": 2.4,
        "model_type": "coder",
        "local": True,
    },
    "vision": {
        "id": "vision",
        "name": "Qwen-VL-3B",
        "display_name": "Qwen2.5-VL-3B-Instruct",
        "endpoint": _VISION_ENDPOINT,
        "capabilities": [
            "vision", "image_analysis", "pid_analysis",
            "document_vision", "ocr", "text_generation",
        ],
        "modalities": ["text", "image"],
        "context_length": 4096,
        "status": "standby",
        "vram_gb": 3.8,
        "model_type": "vision",
        "local": True,
    },
    "embedding": {
        "id": "embedding",
        "name": "BGE-large-en-v1.5",
        "display_name": "BGE-large-en-v1.5 (embeddings)",
        "endpoint": settings.EMBEDDING_MODEL,
        "capabilities": ["embedding"],
        "modalities": ["text"],
        "context_length": 512,
        "status": "online",
        "vram_gb": 1.2,
        "model_type": "embedding",
        "local": True,
    },
    "reranker": {
        "id": "reranker",
        "name": "BGE-reranker-large",
        "display_name": "BGE-reranker-large",
        "capabilities": ["reranking"],
        "endpoint": settings.RERANKER_MODEL,
        "modalities": ["text"],
        "context_length": 512,
        "status": "online",
        "vram_gb": 1.4,
        "model_type": "reranker",
        "local": True,
    },
}

_CAPABILITY_PRIMARY_TYPE = {
    "vision": "vision",
    "image_analysis": "vision",
    "pid_analysis": "vision",
    "document_vision": "vision",
    "ocr": "vision",
    "code_generation": "coder",
    "code_review": "coder",
    "debugging": "coder",
    "reasoning": "general",
    "rag_synthesis": "general",
    "summarization": "general",
    "text_generation": "general",
}


def register_model(model_id: str, model_config: Dict):
    model_registry[model_id] = model_config


def unregister_model(model_id: str):
    if model_id in model_registry:
        del model_registry[model_id]


def list_models() -> List[Tuple[str, Dict]]:
    return [(mid, model) for mid, model in model_registry.items()]


def get_model(model_id: str) -> Optional[Dict]:
    return model_registry.get(model_id)


def update_model_status(model_id: str, status: str):
    if model_id in model_registry:
        model_registry[model_id]["status"] = status


def get_local_models() -> List[Tuple[str, Dict]]:
    """Return only models explicitly marked local=True (sovereignty filter)."""
    return [(mid, m) for mid, m in model_registry.items()
            if m.get("local") is True]


# Capabilities that actually CONSUME image input (others reason over extracted text).
_VISION_CONSUMING_CAPS = {
    "vision", "image_analysis", "pid_analysis", "document_vision", "ocr",
}


def get_models_with_capability(capability: str, modality: str = None) -> List[Tuple[str, Dict]]:
    """Local models whose ``capabilities`` include ``capability`` and whose
    ``modalities`` are compatible with ``modality`` (if provided).

    The image-modality restriction only applies to capabilities that consume image
    input (vision). A text-only reasoning / code model is perfectly valid for the
    synthesis step of a multimodal (image+text) task.
    """
    out = []
    for mid, m in get_local_models():
        if capability not in m.get("capabilities", []):
            continue
        if (capability in _VISION_CONSUMING_CAPS
                and modality
                and "image" in (modality or "")
                and "image" not in m.get("modalities", [])):
            # image-consuming task cannot be served by a text-only model
            continue
        out.append((mid, m))
    # Prefer online/active models, then by model id for stability.
    out.sort(key=lambda kv: (kv[1].get("status") not in ("online", "active"), kv[0]))
    return out


def get_capabilities(model_id: str) -> List[str]:
    m = get_model(model_id)
    return m.get("capabilities", []) if m else []


def capability_label(capability: str) -> str:
    return {
        "vision": "vision / image analysis",
        "image_analysis": "vision / image analysis",
        "pid_analysis": "P&ID analysis",
        "document_vision": "document vision",
        "ocr": "OCR",
        "code_generation": "code generation",
        "code_review": "code review",
        "debugging": "debugging",
        "reasoning": "general reasoning",
        "rag_synthesis": "RAG-grounded synthesis",
        "summarization": "summarization",
        "text_generation": "text generation",
    }.get(capability, capability)
