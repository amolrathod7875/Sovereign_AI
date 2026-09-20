"""Phase 12.1 — Runtime Resilience Tests

Tests for model unavailability, connection failures, timeouts, malformed responses, and recovery.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from httpx import ConnectError

from app.main import app

client = TestClient(app)


# ===================================================================
# CODER FAILURES
# ===================================================================
class TestCoderResilience:
    """Coder endpoint resilience tests."""

    # 1. server unavailable -> 503
    def test_coder_server_unavailable(self):
        """Connection refused should return 503."""
        with patch("agent.coder.run.run_coder_task") as mock_run:
            mock_run.side_effect = ConnectError("Connection refused")
            response = client.post("/api/coder/run", json={"task": "test task"})
            # Updated: Should return exactly 503 (fixed in Phase 12.1)
            assert response.status_code == 503

    # 2. transport failure -> 503
    def test_coder_transport_failure(self):
        """Transport error should return 503."""
        with patch("agent.coder.run.run_coder_task") as mock_run:
            mock_run.side_effect = OSError("Network is unreachable")
            response = client.post("/api/coder/run", json={"task": "test task"})
            # Updated: Should return exactly 503 (fixed in Phase 12.1)
            assert response.status_code == 503

    # 3. timeout -> 504
    def test_coder_timeout_504(self):
        """Application deadline should return 504."""
        with patch("agent.coder.run.run_coder_task") as mock_run:
            mock_run.side_effect = TimeoutError("Deadline exceeded")
            response = client.post("/api/coder/run", json={"task": "test task"})
            assert response.status_code == 504

    # 4. malformed upstream JSON -> controlled failure
    def test_coder_malformed_json(self):
        """Malformed JSON from server should be handled gracefully."""
        # This tests the ModelClient layer that coder uses internally
        from app.models.client import ModelClient
        with patch.object(ModelClient, 'generate') as mock_generate:
            mock_generate.side_effect = ValueError("Invalid JSON response")
            from agent.coder.model import complete
            with pytest.raises(Exception):
                complete([{"role": "user", "content": "test"}])

    # 5. missing completion payload -> controlled failure
    def test_coder_missing_completion_payload(self):
        """Missing fields in completion response should raise a controlled error.

        This exercises the validation inside ModelClient.generate() by mocking
        the RAW HTTP response, NOT ModelClient.generate itself.  This ensures
        the response-parsing boundary is validated end-to-end.
        """
        from app.models.client import ModelClient, ModelClientError
        from unittest.mock import AsyncMock, MagicMock

        # Simulate a raw upstream response that is missing the 'choices' field
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()  # no HTTP error
        mock_response.json.return_value = {"invalid": "response"}  # missing 'choices'

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock,
                   return_value=mock_response):
            from agent.coder.model import complete
            # The malformed payload must be rejected, never treated as valid
            with pytest.raises((ModelClientError, ValueError)):
                complete([{"role": "user", "content": "test"}])

    # 6. recovery after previous failure
    def test_coder_recovery_after_failure(self):
        """Failed request must not permanently mark model unavailable."""
        # First call fails
        with patch("agent.coder.run.run_coder_task") as mock_run:
            mock_run.side_effect = ConnectError("Failed")
            response1 = client.post("/api/coder/run", json={"task": "test task"})
            assert response1.status_code == 503

            # Second call should succeed (no persistent availability state)
            mock_run.side_effect = None
            mock_run.return_value = {
                "status": "COMPLETED",
                "external_calls": 0
            }
            response2 = client.post("/api/coder/run", json={"task": "test task"})
            assert response2.status_code == 200


# ===================================================================
# VISION FAILURES
# ===================================================================
class TestVisionResilience:
    """Vision endpoint resilience tests."""

    # 7. server unavailable -> 503
    def test_vision_server_unavailable(self):
        """Connection error should return 503."""
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            mock_analyze.side_effect = ConnectError("Connection refused")
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general"
            })
            assert response.status_code == 503
            detail = response.json()["detail"]
            assert "8003" in detail or "vision" in detail.lower()

    # 8. transport failure -> 503
    def test_vision_transport_failure(self):
        """Transport error should return 503."""
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            mock_analyze.side_effect = OSError("Network is unreachable")
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general"
            })
            assert response.status_code == 503

    # 9. timeout -> controlled timeout status
    def test_vision_timeout(self):
        """Timeout should return appropriate error status."""
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            mock_analyze.side_effect = TimeoutError("Timeout")
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general"
            })
        # Timeout must return 504 (caught before OSError), never 503
        assert response.status_code == 504

    # 10. malformed response -> controlled failure
    def test_vision_malformed_response(self):
        """Malformed VLM response should return 502; user input errors 400."""
        from agent.tools.vision import VisionUpstreamResponseError

        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            # Test 1: Upstream model returned malformed JSON -> 502
            mock_analyze.side_effect = VisionUpstreamResponseError("Invalid JSON")
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general"
            })
            # VisionUpstreamResponseError -> HTTP 502 (upstream response issue)
            assert response.status_code == 502

            # Test 2: User input error -> ValueError -> 400
            mock_analyze.side_effect = ValueError("unsupported file type")
            response2 = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general"
            })
            # ValueError -> HTTP 400 (user input issue)
            assert response2.status_code == 400

    # 11. missing completion payload -> controlled failure
    def test_vision_missing_completion_payload(self):
        """Missing expected fields should be handled."""
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            # Return response missing required fields
            mock_analyze.return_value = {"invalid": "response"}
            response = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general"
            })
            # Should handle gracefully, not crash
            assert response.status_code == 200

    # 12. recovery after previous failure
    def test_vision_recovery_after_failure(self):
        """Failed request must not permanently mark model unavailable."""
        with patch("agent.tools.vision.analyze_image") as mock_analyze:
            # First call fails
            mock_analyze.side_effect = ConnectError("Failed")
            response1 = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general"
            })
            
            # Second call should succeed (no persistent state)
            mock_analyze.side_effect = None
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
            response2 = client.post("/api/vision/analyze", json={
                "file_path": "test.jpg",
                "analysis_type": "general"
            })
            assert response2.status_code == 200


# ===================================================================
# SYSTEM STATUS
# ===================================================================
class TestSystemResilience:
    """System status endpoint resilience tests."""

    # 13. health probe does not block event loop indefinitely
    def test_health_probe_timeout_safe(self):
        """Health check should not block indefinitely."""
        import time
        from unittest.mock import patch

        start = time.time()
        response = client.get("/api/system/health")
        elapsed = time.time() - start
        # Should respond quickly, even if underlying probes fail
        assert response.status_code == 200
        assert elapsed < 5.0  # Should not block

    # 14. model health failure does not crash /api/system/status
    def test_system_status_health_failure_graceful(self):
        """Model health failures should not crash system status."""
        from app.models.registry import get_model
        with patch("app.models.registry.get_model") as mock_get_model:
            # Simulate models being offline/unavailable
            mock_get_model.side_effect = lambda model_id: None

            response = client.get("/api/system/status")
            # Should not crash, should return some status
            assert response.status_code == 200
            data = response.json()
            assert "services" in data or "components" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
