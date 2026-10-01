"""Phase 18.3 — ModelClient performance metrics tests."""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.models.client import ModelClient, ModelPerformanceMetrics, ModelClientError, ModelBusyError


def _make_response(data: dict, status_code: int = 200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.raise_for_status = MagicMock()
    mock.json = MagicMock(return_value=data)
    return mock


# ---------------------------------------------------------------------------
# 1. generate() still returns only a string
# ---------------------------------------------------------------------------
def test_generate_returns_string():
    client = ModelClient("test-model", "http://127.0.0.1:9999")
    with patch.object(client, "client") as mock_client:
        mock_post = AsyncMock()
        mock_post.return_value = _make_response({
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "performance": {"inference_seconds": 0.5, "tokens_per_second": 10.0},
        })
        mock_client.post = mock_post

        result = asyncio.run(client.generate([{"role": "user", "content": "hi"}]))
    assert result == "hello"


# ---------------------------------------------------------------------------
# 2. generate_with_metrics returns content + usage + performance
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_with_metrics_returns_full_result():
    client = ModelClient("test-model", "http://127.0.0.1:9999")
    with patch.object(client, "client") as mock_client:
        mock_post = AsyncMock()
        mock_post.return_value = _make_response({
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "performance": {"inference_seconds": 0.5, "tokens_per_second": 10.0},
        })
        mock_client.post = mock_post

        result = await client.generate_with_metrics([{"role": "user", "content": "hi"}])
    assert result["content"] == "hi"
    assert result["usage"] == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert result["performance"]["inference_seconds"] == 0.5
    assert result["performance"]["tokens_per_second"] == 10.0


# ---------------------------------------------------------------------------
# 3. Missing performance block -> metrics null
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_with_metrics_handles_missing_performance():
    client = ModelClient("test-model", "http://127.0.0.1:9999")
    with patch.object(client, "client") as mock_client:
        mock_post = AsyncMock()
        mock_post.return_value = _make_response({
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })
        mock_client.post = mock_post

        result = await client.generate_with_metrics([{"role": "user", "content": "hi"}])
    assert result["content"] == "hi"
    assert result["performance"]["inference_seconds"] is None
    assert result["performance"]["tokens_per_second"] is None


# ---------------------------------------------------------------------------
# 4. Missing usage block -> metrics null
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_with_metrics_handles_missing_usage():
    client = ModelClient("test-model", "http://127.0.0.1:9999")
    with patch.object(client, "client") as mock_client:
        mock_post = AsyncMock()
        mock_post.return_value = _make_response({
            "choices": [{"message": {"content": "hi"}}],
        })
        mock_client.post = mock_post

        result = await client.generate_with_metrics([{"role": "user", "content": "hi"}])
    assert result["content"] == "hi"
    assert result["usage"]["prompt_tokens"] is None
    assert result["usage"]["completion_tokens"] is None


# ---------------------------------------------------------------------------
# 5. Malformed performance block does not break content generation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_with_metrics_handles_malformed_performance():
    client = ModelClient("test-model", "http://127.0.0.1:9999")
    with patch.object(client, "client") as mock_client:
        mock_post = AsyncMock()
        mock_post.return_value = _make_response({
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "performance": "not_a_dict",
        })
        mock_client.post = mock_post

        result = await client.generate_with_metrics([{"role": "user", "content": "hi"}])
    assert result["content"] == "hi"


# ---------------------------------------------------------------------------
# 6. 429 -> ModelBusyError
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_with_metrics_429_raises_busy():
    client = ModelClient("test-model", "http://127.0.0.1:9999")
    with patch.object(client, "client") as mock_client:
        mock_post = AsyncMock()
        mock_post.return_value = _make_response({}, status_code=429)
        mock_client.post = mock_post

        with pytest.raises(Exception):
            await client.generate_with_metrics([{"role": "user", "content": "hi"}])
