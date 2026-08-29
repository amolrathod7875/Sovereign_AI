"""Local Qwen Coder client.

Reuses the existing OpenAI-compatible model client (``app.models.client.ModelClient``)
so the coding agent talks to the same ``scripts/serve_model.py`` server that the rest
of the platform uses. No cloud SDK, no external model calls.
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

from app.models.client import ModelClient
from app.config import settings
from agent.coder.config import CODER_MODEL_ID, CODER_ENDPOINT, CODER_MODEL_TIMEOUT

logger = logging.getLogger(__name__)


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
            return await client.generate(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
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
