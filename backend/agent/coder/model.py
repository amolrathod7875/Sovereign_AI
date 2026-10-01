"""Local Qwen Coder client.

Reuses the existing OpenAI-compatible model client (``app.models.client.ModelClient``)
so the coding agent talks to the same ``scripts/serve_model.py`` server that the rest
of the platform uses. No cloud SDK, no external model calls.
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

from app.models.client import ModelClient, ModelPerformanceMetrics
from app.config import settings
from agent.coder.config import CODER_MODEL_ID, CODER_ENDPOINT, CODER_MODEL_TIMEOUT

logger = logging.getLogger(__name__)

# Import the exception that ModelClient should raise
from app.models.client import ModelClientError


_model_metrics: List[Dict[str, Any]] = []


def _reset_metrics() -> None:
    _model_metrics.clear()


def get_model_metrics() -> List[Dict[str, Any]]:
    return list(_model_metrics)


def _aggregate_metrics(metrics_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not metrics_list:
        return None
    total_completion = sum(m.get("completion_tokens") or 0 for m in metrics_list)
    total_inference = sum(m.get("inference_seconds") or 0.0 for m in metrics_list)
    prompt_tokens = metrics_list[0].get("prompt_tokens")
    completion_tokens = total_completion or None
    total_tokens = metrics_list[0].get("total_tokens")
    inference_seconds = total_inference if total_inference > 0 else None
    tokens_per_second = (
        round(total_completion / total_inference, 2)
        if total_completion > 0 and total_inference > 0
        else None
    )
    return {
        "model_calls": len(metrics_list),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "inference_seconds": round(inference_seconds, 3) if inference_seconds is not None else None,
        "tokens_per_second": tokens_per_second,
    }


def complete(
    messages: List[Dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 2048,
    timeout: float = CODER_MODEL_TIMEOUT,
) -> str:
    """Synchronous chat completion against the local Qwen Coder server."""

    async def _call() -> str:
        client = ModelClient(CODER_MODEL_ID, CODER_ENDPOINT)
        try:
            result = await client.generate_with_metrics(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            _model_metrics.append(result.get("performance") or {})
            return result["content"]
        finally:
            await client.close()

    return asyncio.run(_call())


def chat(
    system: Optional[str],
    user: str,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> str:
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    return complete(messages, temperature=temperature, max_tokens=max_tokens)
