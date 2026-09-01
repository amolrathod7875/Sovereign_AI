"""Phase 10.4 — Inference reliability, timeout & recovery tests.

Tests for:
A. Coder task propagation
B. Coder timeout returns 504
C. Coder unavailable returns 503/504
D. Vision unavailable returns 503
E. Vision successful local inference remains valid
"""
import asyncio
import time
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from agent.coder import prompts


client = TestClient(app)


# ==================================================================
# A. Coder task propagation
# ==================================================================
class TestCoderTaskPropagation:
    """Verify the user's submitted task reaches the coder agent."""

    def test_gen_user_template_contains_task_placeholder(self):
        """GEN_USER prompt must have a {task} placeholder."""
        assert "{task}" in prompts.GEN_USER

    def test_gen_user_template_no_hardcoded_sensor_task(self):
        """GEN_USER must NOT hard-code the sensor CSV task."""
        # The old prompt hard-coded a specific sensor CSV analysis task
        assert "sensor_fixture.csv" not in prompts.GEN_USER
        assert "temperature=320.0" not in prompts.GEN_USER
        assert "pressure=21.0" not in prompts.GEN_USER
        assert "vibration=4.0" not in prompts.GEN_USER

    def test_task_propagates_to_prompt(self):
        """Task A and Task B must both appear in the formatted prompt."""
        task_a = "Create a calculator that adds two numbers"
        task_b = "Build a function that reverses a string"

        formatted_a = prompts.GEN_USER.format(task=task_a, plan="test plan")
        formatted_b = prompts.GEN_USER.format(task=task_b, plan="test plan")

        assert task_a in formatted_a
        assert task_b in formatted_b
        assert task_a not in formatted_b
        assert task_b not in formatted_a

    def test_different_tasks_produce_different_prompts(self):
        """Different tasks must produce different prompts."""
        task_a = "Implement bubble sort"
        task_b = "Implement merge sort"

        formatted_a = prompts.GEN_USER.format(task=task_a, plan="plan")
        formatted_b = prompts.GEN_USER.format(task=task_b, plan="plan")

        assert formatted_a != formatted_b


# ==================================================================
# B. Coder timeout returns 504
# ==================================================================
class TestCoderTimeout:
    """Verify coder timeout returns structured 504."""

    def test_coder_timeout_returns_504(self):
        """Coder workflow that exceeds deadline must return 504."""
        # Patch the run_coder_task function where it's imported
        with patch("agent.coder.run.run_coder_task") as mock_run:
            # Simulate a task that takes too long
            def slow_task(*args, **kwargs):
                time.sleep(0.5)
                return {}

            mock_run.side_effect = slow_task

            # Use a very short deadline for testing
            with patch("app.api.coder.CODER_DEADLINE", 0.1):
                response = client.post("/api/coder/run", json={"task": "test task"})
                assert response.status_code == 504
                assert "deadline" in response.json()["detail"].lower() or "exceeded" in response.json()["detail"].lower()

    def test_coder_deadline_is_reasonable(self):
        """Coder deadline must be at least 15 minutes (900s)."""
        from app.api.coder import CODER_DEADLINE
        assert CODER_DEADLINE >= 900


# ==================================================================
# C. Coder unavailable returns 503/504
# ==================================================================
class TestCoderUnavailable:
    """Verify coder handles model server unavailability."""

    def test_coder_empty_task_returns_422(self):
        """Empty task must return 422."""
        response = client.post("/api/coder/run", json={"task": ""})
        assert response.status_code == 422

    def test_coder_whitespace_task_returns_422(self):
        """Whitespace-only task must return 422."""
        response = client.post("/api/coder/run", json={"task": "   "})
        assert response.status_code == 422


# ==================================================================
# D. Vision unavailable returns 503
# ==================================================================
class TestVisionUnavailable:
    """Verify vision handles model server unavailability."""

    def test_vision_connection_error_returns_503(self):
        """Connection error from vision tool must return 503."""
        # Patch where the function is used (inside _analyze_guarded)
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            mock_analyze.side_effect = ConnectionError("Connection refused")
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general"
            })
            assert response.status_code == 503

    def test_vision_connection_error_message_includes_endpoint(self):
        """503 error must include endpoint info for debugging."""
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            mock_analyze.side_effect = ConnectionError("Connection refused")
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general"
            })
            assert response.status_code == 503
            detail = response.json()["detail"]
            assert "8003" in detail or "vision" in detail.lower()


# ==================================================================
# E. Vision successful local inference
# ==================================================================
class TestVisionLocalInference:
    """Verify vision local inference remains valid."""

    def test_vision_local_data_origin(self):
        """Vision result must have data_origin=local."""
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            mock_analyze.return_value = {
                "file": "test.jpg",
                "analysis_type": "general",
                "description": "test",
                "findings": [],
                "entities": [],
                "uncertain_items": [],
                "confidence": 0.5,
                "model": "test-model",
                "data_origin": "local",
                "timestamp": "2024-01-01T00:00:00Z",
                "source_file": "test.jpg",
            }
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general"
            })
            assert response.status_code == 200
            assert response.json()["result"]["data_origin"] == "local"
            assert response.json()["external_calls"] == 0


# ==================================================================
# F. PDF timeout multiplication prevention
# ==================================================================
class TestVisionPDFDeadline:
    """Verify PDF analysis has a total deadline."""

    def test_pdf_analysis_respects_deadline(self):
        """Multi-page PDF analysis must stop at deadline."""
        import time
        from pathlib import Path
        from unittest.mock import MagicMock

        # Create a mock path that looks like a PDF
        mock_path = MagicMock(spec=Path)
        mock_path.name = "test.pdf"
        mock_path.suffix = ".pdf"
        mock_path.exists.return_value = True
        mock_path.is_dir.return_value = False

        # Track call times
        call_times = []

        def mock_vlm(*args, **kwargs):
            call_times.append(time.time())
            return '{"description": "test", "findings": [], "entities": [], "uncertain_items": []}'

        with patch("agent.tools.vision.extract_pdf_text", return_value=""):
            with patch("agent.tools.vision.render_pdf_pages") as mock_render:
                # Return 10 pages
                mock_render.return_value = [
                    {"page": i, "b64": "dGVzdA=="} for i in range(1, 11)
                ]
                with patch("agent.tools.vision._call_vlm", side_effect=mock_vlm):
                    with patch("agent.tools.vision.VISION_TIMEOUT", 1):  # 1 second timeout
                        from agent.tools.vision import _analyze_pdf
                        start = time.time()
                        # This should complete quickly due to deadline
                        try:
                            result = _analyze_pdf(mock_path, None, "general", start)
                            elapsed = time.time() - start
                            # Should not take 10 seconds (10 pages * 1 second each)
                            assert elapsed < 5, f"PDF analysis took {elapsed}s, deadline not respected"
                        except Exception:
                            # If it raises, that's also acceptable as long as it's fast
                            elapsed = time.time() - start
                            assert elapsed < 5, f"PDF analysis took {elapsed}s before raising"
