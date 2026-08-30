"""Phase 7.1 — Security hardening tests for the Piston sandbox endpoint.

Covers the two hardening fixes:
  * Fix 1 (env secrets) is verified by .gitignore / git ls-files (see report).
  * Fix 2 (Piston endpoint validation) is verified here:
      - internal/local Piston URLs are accepted (piston, localhost, 127.0.0.1)
      - external Piston URLs are rejected (example.com, api.openai.com)
      - existing Piston execution still works under the network guard (mocked)
      - the agent's local sandbox still works
      - NetworkGuard still blocks external sockets (defense in depth)
"""
import asyncio
import os

import pytest

from app.tools.python_tool import (
    is_internal_piston_url,
    validate_piston_url,
    execute_in_sandbox,
    get_sandbox_status,
)
from agent.security.netguard import no_network
from agent.coder import sandbox as coder_sandbox

from unittest.mock import AsyncMock, patch


# ---------------------------------------------------------------------------
# Piston URL acceptance matrix
# ---------------------------------------------------------------------------
def test_piston_internal_docker_hostname_allowed():
    assert is_internal_piston_url("http://piston:2000") is True


def test_piston_localhost_allowed():
    assert is_internal_piston_url("http://localhost:2000") is True
    assert is_internal_piston_url("http://127.0.0.1:2000") is True


def test_piston_external_fqdn_rejected():
    assert is_internal_piston_url("https://example.com") is False
    assert is_internal_piston_url("https://api.openai.com/v1") is False
    assert is_internal_piston_url("http://1.2.3.4:2000") is False


def test_validate_piston_url_rejects_external():
    with pytest.raises(ConnectionError):
        validate_piston_url("https://api.openai.com/v1")
    with pytest.raises(ConnectionError):
        validate_piston_url("https://example.com")
    # internal URLs must pass without raising
    validate_piston_url("http://piston:2000")
    validate_piston_url("http://localhost:2000")
    validate_piston_url("http://127.0.0.1:2000")


# ---------------------------------------------------------------------------
# Existing Piston behavior still works (mocked, under NetworkGuard)
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self.text = "ok"
        self._payload = payload or {
            "run": {"stdout": "258", "stderr": "", "exit_code": 0,
                    "execution_time": 5}
        }

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.post = AsyncMock(return_value=_FakeResponse())
        self.get = AsyncMock(return_value=_FakeResponse(
            status_code=200, payload={"online": True}))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def test_existing_piston_execution_still_works(monkeypatch):
    monkeypatch.setattr(
        "app.tools.python_tool.settings.PISTON_URL", "http://localhost:2000")
    with patch("app.tools.python_tool.httpx.AsyncClient", _FakeAsyncClient):
        result = asyncio.run(execute_in_sandbox("print(258)", "python", timeout=5))
    assert result["exit_code"] == 0, result
    assert "258" in result["stdout"], result
    assert result["execution_time_ms"] == 5


def test_existing_piston_status_still_works(monkeypatch):
    monkeypatch.setattr(
        "app.tools.python_tool.settings.PISTON_URL", "http://piston:2000")
    with patch("app.tools.python_tool.httpx.AsyncClient", _FakeAsyncClient):
        status = asyncio.run(get_sandbox_status())
    assert status["status"] == "online", status


def test_external_piston_url_blocks_execution(monkeypatch):
    monkeypatch.setattr(
        "app.tools.python_tool.settings.PISTON_URL", "https://api.openai.com/v1")
    with pytest.raises(ConnectionError):
        asyncio.run(execute_in_sandbox("print(1)", "python", timeout=5))


# ---------------------------------------------------------------------------
# Existing agent sandbox still works (real local subprocess sandbox)
# ---------------------------------------------------------------------------
def test_existing_agent_sandbox_still_works():
    res = coder_sandbox.execute_code(
        str(__import__("tempfile").mkdtemp()), "print('sov_ok')", timeout=10)
    assert res["exit_code"] == 0, res
    assert "sov_ok" in res["stdout"], res


# ---------------------------------------------------------------------------
# NetworkGuard external blocking still works (defense in depth)
# ---------------------------------------------------------------------------
def test_networkguard_blocks_external_socket():
    import socket
    with pytest.raises(Exception):
        with no_network():
            socket.create_connection(("8.8.8.8", 53), timeout=2)
    # an external FQDN must also be blocked (would require DNS / network)
    with pytest.raises(Exception):
        with no_network():
            socket.create_connection(("example.com", 80), timeout=2)


def test_networkguard_allows_loopback():
    import socket
    import threading

    # Spin up a real ephemeral loopback listener so the connect succeeds
    # deterministically (no dependency on an external server being up).
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _accept():
        try:
            conn, _ = srv.accept()
            conn.close()
        except OSError:
            pass

    t = threading.Thread(target=_accept, daemon=True)
    t.start()
    try:
        with no_network() as guard:
            # Must be delegated to the real socket (allowed), NOT blocked.
            c = socket.create_connection(("127.0.0.1", port), timeout=3)
            c.close()
        assert guard.external_calls == 0
        assert guard.blocked == []
    finally:
        srv.close()
        t.join(timeout=2)


@pytest.fixture(autouse=True)
def _offline():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
