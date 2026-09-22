"""Phase 12.3B1 — API 429 Error Propagation Tests.

Verifies that upstream model-server HTTP 429 responses are propagated as
HTTP 429 through both the coder and vision API endpoints, with no automatic
retries, and that existing error behaviour is preserved.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app
from app.models.client import ModelBusyError

client = TestClient(app)


# ===================================================================
# CODER 429 PROPAGATION
# ===================================================================
class TestCoder429Propagation:
    """Coder endpoint must return 429, not 500, on model busy."""

    def test_coder_model_busy_returns_429(self):
        """ModelBusyError from upstream -> /api/coder/run returns 429."""
        with patch("agent.coder.run.run_coder_task") as mock_run:
            mock_run.side_effect = ModelBusyError("GPU busy")
            response = client.post("/api/coder/run", json={"task": "test task"})
            assert response.status_code == 429
            detail = response.json()["detail"]
            assert "busy" in detail.lower() or "gpu" in detail.lower()

    def test_coder_model_busy_no_retry(self):
        """A 429 must not be retried automatically."""
        call_count = {"n": 0}

        def counting_busy(*args, **kwargs):
            call_count["n"] += 1
            raise ModelBusyError("GPU busy")

        with patch("agent.coder.run.run_coder_task", side_effect=counting_busy):
            response = client.post("/api/coder/run", json={"task": "test task"})
            assert response.status_code == 429
            assert call_count["n"] == 1

    def test_coder_preserves_existing_503(self):
        """Connection errors must still return 503."""
        from httpx import ConnectError

        with patch("agent.coder.run.run_coder_task") as mock_run:
            mock_run.side_effect = ConnectError("Connection refused")
            response = client.post("/api/coder/run", json={"task": "test task"})
            assert response.status_code == 503

    def test_coder_preserves_existing_504(self):
        """Timeouts must still return 504."""
        with patch("agent.coder.run.run_coder_task") as mock_run:
            mock_run.side_effect = TimeoutError("Deadline exceeded")
            response = client.post("/api/coder/run", json={"task": "test task"})
            assert response.status_code == 504

    def test_coder_preserves_existing_500_on_unexpected(self):
        """Unexpected exceptions must still return 500."""
        with patch("agent.coder.run.run_coder_task") as mock_run:
            mock_run.side_effect = RuntimeError("unexpected")
            response = client.post("/api/coder/run", json={"task": "test task"})
            assert response.status_code == 500


# ===================================================================
# VISION 429 PROPAGATION
# ===================================================================
class TestVision429Propagation:
    """Vision endpoint must return 429, not 500, on model busy."""

    def test_vision_model_busy_returns_429(self):
        """VisionModelBusyError -> /api/vision/analyze returns 429."""
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            from agent.tools.vision import VisionModelBusyError
            mock_analyze.side_effect = VisionModelBusyError("GPU busy")
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general",
            })
            assert response.status_code == 429
            detail = response.json()["detail"]
            assert "busy" in detail.lower() or "gpu" in detail.lower()

    def test_vision_model_busy_retry_after_header(self):
        """429 response should include Retry-After."""
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            from agent.tools.vision import VisionModelBusyError
            mock_analyze.side_effect = VisionModelBusyError("GPU busy")
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general",
            })
            assert response.status_code == 429
            assert response.headers.get("Retry-After") == "5"

    def test_vision_model_busy_no_retry(self):
        """A 429 must not trigger automatic retries."""
        from agent.tools.vision import VisionModelBusyError

        call_count = {"n": 0}

        def counting_busy(*args, **kwargs):
            call_count["n"] += 1
            raise VisionModelBusyError("GPU busy")

        with patch("agent.tools.vision.analyze_image", side_effect=counting_busy):
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general",
            })
            assert response.status_code == 429
            assert call_count["n"] == 1

    def test_vision_preserves_existing_503(self):
        """Connection errors must still return 503."""
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            mock_analyze.side_effect = ConnectionError("Connection refused")
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general",
            })
            assert response.status_code == 503

    def test_vision_preserves_existing_502(self):
        """Upstream response errors must still return 502."""
        from agent.tools.vision import VisionUpstreamResponseError

        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            mock_analyze.side_effect = VisionUpstreamResponseError("bad JSON")
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general",
            })
            assert response.status_code == 502

    def test_vision_preserves_existing_504(self):
        """Timeouts must still return 504."""
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            mock_analyze.side_effect = TimeoutError("Timeout")
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general",
            })
            assert response.status_code == 504


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
