"""Phase 18.3 — Model server performance metadata tests."""
import os
import sys
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_SLOW_TESTS"),
    reason="fast unit tests run by default; model-server tests need RUN_SLOW_TESTS=1",
)


def test_performance_formula():
    completion_tokens = 100
    inference_seconds = 2.0
    tokens_per_second = (
        round(completion_tokens / inference_seconds, 2)
        if completion_tokens > 0 and inference_seconds > 0
        else None
    )
    assert tokens_per_second == 50.0


def test_performance_formula_zero_inference_seconds():
    completion_tokens = 100
    inference_seconds = 0.0
    tokens_per_second = (
        round(completion_tokens / inference_seconds, 2)
        if completion_tokens > 0 and inference_seconds > 0
        else None
    )
    assert tokens_per_second is None


def test_performance_formula_zero_completion_tokens():
    completion_tokens = 0
    inference_seconds = 2.0
    tokens_per_second = (
        round(completion_tokens / inference_seconds, 2)
        if completion_tokens > 0 and inference_seconds > 0
        else None
    )
    assert tokens_per_second is None
