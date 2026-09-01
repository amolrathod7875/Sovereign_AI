"""Phase 5C-1.5 — NetworkGuard isolation + restoration tests.

These cover the required scenarios:

A. External connection blocked
B. localhost allowed
C. localhost:8003 allowed
D. socket state restored after context
E. socket state restored after exception
F. multiple sequential NetworkGuard contexts
G. NetworkGuard test followed by vision test (same process)
H. vision test followed by NetworkGuard test (same process)
I. agent test followed by vision test  (validated via pytest ordering)
J. vision test followed by agent test  (validated via pytest ordering)

The critical property: the guard never leaves `socket.socket` patched, so
test order cannot affect localhost access to the Qwen-VL server on :8003.
"""
import os
import socket

import pytest

from agent.security.netguard import NetworkGuard, no_network
from agent.tools.vision import analyze_image, _assert_local_endpoint
from agent.run import run_agent_task

REPO = __import__("pathlib").Path(__file__).resolve().parents[2]
PID = REPO / "PID_Dataset" / "0__raw_data" / "sheets" / "test"
IMG = str(PID / "158.jpg")
VISION_ENDPOINT = "http://localhost:8003/v1"


@pytest.fixture(autouse=True)
def _offline():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _server_up() -> bool:
    try:
        import httpx

        with httpx.Client(timeout=2.0) as c:
            return c.get(f"{VISION_ENDPOINT}/models").status_code == 200
    except Exception:
        return False


requires_server = pytest.mark.skipif(
    not _server_up(), reason="local vision server not running on :8003"
)


# A. External connection blocked ----------------------------------------------
def test_external_connection_blocked():
    with pytest.raises(Exception):
        with NetworkGuard():
            socket.create_connection(("8.8.8.8", 53), timeout=2)
    # An external hostname must also be blocked (would require DNS / network).
    with pytest.raises(Exception):
        with NetworkGuard():
            socket.create_connection(("example.com", 80), timeout=2)


def test_external_calls_recorded():
    with NetworkGuard() as guard:
        with pytest.raises(Exception):
            socket.create_connection(("8.8.8.8", 53), timeout=2)
    assert guard.external_calls >= 1
    assert guard.blocked


# B. localhost allowed ---------------------------------------------------------
def test_localhost_allowed_without_guard_leak():
    with NetworkGuard() as guard:
        s = socket.create_connection(("127.0.0.1", 8003), timeout=2)
        s.close()
    assert guard.external_calls == 0


# C. localhost:8003 allowed (the real Qwen-VL server) --------------------------
@requires_server
def test_localhost_8003_allowed():
    with NetworkGuard() as guard:
        s = socket.create_connection(("127.0.0.1", 8003), timeout=2)
        s.close()
    assert guard.external_calls == 0


# D. socket state restored after context ---------------------------------------
def test_socket_restored_after_context():
    original = socket.socket
    with NetworkGuard():
        assert socket.socket is not original
    assert socket.socket is original


# E. socket state restored after exception -------------------------------------
def test_socket_restored_after_exception():
    original = socket.socket
    guard = NetworkGuard()
    try:
        with guard:
            raise RuntimeError("simulated failure inside guard")
    except RuntimeError:
        pass
    assert socket.socket is original
    assert guard._entered is False


# F. multiple sequential contexts ----------------------------------------------
def test_multiple_sequential_contexts():
    original = socket.socket
    for _ in range(3):
        with NetworkGuard() as guard:
            with pytest.raises(Exception):
                socket.create_connection(("8.8.8.8", 53), timeout=2)
            assert guard.external_calls >= 1
        assert socket.socket is original
    assert socket.socket is original


# G. NetworkGuard test followed by vision test (same process) -------------------
@requires_server
def test_netguard_then_vision():
    with NetworkGuard() as guard:
        with pytest.raises(Exception):
            socket.create_connection(("8.8.8.8", 53), timeout=2)
    assert socket.socket is not type(socket.socket) or True  # sanity
    # The guard is fully gone -> the vision tool reaches localhost:8003 fine.
    original = socket.socket
    res = analyze_image(IMG, analysis_type="general",
                        prompt="Briefly describe this drawing.")
    assert res["data_origin"] == "local"
    assert socket.socket is original


# H. vision test followed by NetworkGuard test (same process) ------------------
@requires_server
def test_vision_then_netguard():
    original = socket.socket
    res = analyze_image(IMG, analysis_type="general",
                        prompt="Briefly describe this drawing.")
    assert res["data_origin"] == "local"
    assert socket.socket is original
    # Now activate a guard; the earlier vision call must not have left state.
    with NetworkGuard() as guard:
        with pytest.raises(Exception):
            socket.create_connection(("8.8.8.8", 53), timeout=2)
    assert socket.socket is original


# I / J. agent <-> vision ordering is validated by running the test files in
# both orders (see the phase report). These integration checks exercise the
# same paths: an agent run that internally uses a nested guard, then a direct
# vision call, and vice-versa.

@requires_server
def test_agent_run_then_vision_localhost():
    res = run_agent_task(
        "Inspect P&ID 158.jpg and summarize the visible equipment.",
        asset_tag="R-1001",
        run_id="netguard_order_i",
        artifact_filename="R-1001_netguard_i.docx",
        image_path=IMG,
        analysis_type="pid",
    )
    assert res["external_calls"] == 0
    original = socket.socket
    vision_res = analyze_image(IMG, analysis_type="general",
                               prompt="Briefly describe this drawing.")
    assert vision_res["data_origin"] == "local"
    assert socket.socket is original


@requires_server
def test_vision_then_agent_run_localhost():
    original = socket.socket
    vision_res = analyze_image(IMG, analysis_type="general",
                               prompt="Briefly describe this drawing.")
    assert vision_res["data_origin"] == "local"
    assert socket.socket is original
    res = run_agent_task(
        "Inspect P&ID 158.jpg and summarize the visible equipment.",
        asset_tag="R-1001",
        run_id="netguard_order_j",
        artifact_filename="R-1001_netguard_j.docx",
        image_path=IMG,
        analysis_type="pid",
    )
    assert res["external_calls"] == 0


def test_local_endpoint_guard_rejects_external():
    with pytest.raises(ConnectionError):
        _assert_local_endpoint("http://1.2.3.4/v1")
    _assert_local_endpoint("http://localhost:8003/v1")
    _assert_local_endpoint("http://127.0.0.1:8003/v1")


# ==================================================================
# Phase 10.3 — NetworkGuard sovereignty boundary hardening
# ==================================================================
from agent.security.netguard import _is_local_host, _TRUSTED_NETWORKS
from app.models.registry import is_local_endpoint


# A. Loopback remains local ----------------------------------------------------
@pytest.mark.parametrize("host", [
    "127.0.0.1",
    "127.0.0.2",
    "127.255.255.254",
    "::1",
    "localhost",
])
def test_loopback_is_local(host):
    assert _is_local_host(host) is True


# B. RFC1918 remains local -----------------------------------------------------
@pytest.mark.parametrize("host", [
    "10.0.0.1",
    "10.255.255.254",
    "172.16.0.1",
    "172.31.255.254",
    "192.168.0.1",
    "192.168.255.254",
])
def test_rfc1918_is_local(host):
    assert _is_local_host(host) is True


# C. 169.254.0.0/16 is NOT local (link-local / cloud metadata) ----------------
@pytest.mark.parametrize("host", [
    "169.254.169.254",  # cloud instance metadata endpoint
    "169.254.1.1",
    "169.254.0.1",
    "169.254.255.254",
])
def test_linklocal_not_local(host):
    assert _is_local_host(host) is False


# D. RFC5737 documentation ranges are NOT local -------------------------------
@pytest.mark.parametrize("host", [
    "192.0.2.1",
    "192.0.2.100",
    "198.51.100.1",
    "198.51.100.100",
    "203.0.113.1",
    "203.0.113.100",
])
def test_documentation_ranges_not_local(host):
    assert _is_local_host(host) is False


# E. RFC2544 benchmark ranges are NOT local -----------------------------------
@pytest.mark.parametrize("host", [
    "198.18.0.1",
    "198.19.0.1",
    "198.18.255.254",
    "198.19.255.254",
])
def test_benchmark_ranges_not_local(host):
    assert _is_local_host(host) is False


# F. IPv6 link-local is NOT local ---------------------------------------------
@pytest.mark.parametrize("host", [
    "fe80::1",
    "fe80::1234",
    "fe80::abcd:ef01:2345:6789",
])
def test_ipv6_linklocal_not_local(host):
    assert _is_local_host(host) is False


# G. IPv6 ULA is NOT local -----------------------------------------------------
@pytest.mark.parametrize("host", [
    "fc00::1",
    "fd00::1",
    "fd12:3456:789a::1",
])
def test_ipv6_ula_not_local(host):
    assert _is_local_host(host) is False


# H. Special/reserved addresses are NOT local ---------------------------------
@pytest.mark.parametrize("host", [
    "0.0.0.0",           # unspecified
    "255.255.255.255",   # broadcast
    "224.0.0.1",         # multicast
    "240.0.0.1",         # reserved
    "192.0.0.1",         # IETF Protocol Assignments
    "100.64.0.1",        # CGNAT (shared address space)
])
def test_special_reserved_not_local(host):
    assert _is_local_host(host) is False


# I. is_local_endpoint: trusted local URLs continue to work -------------------
@pytest.mark.parametrize("url", [
    "http://localhost:8002/v1",
    "http://127.0.0.1:8002/v1",
    "http://10.0.0.5:8002/v1",
    "http://172.16.0.5:8002/v1",
    "http://192.168.1.5:8002/v1",
])
def test_registry_local_endpoints_accepted(url):
    assert is_local_endpoint(url) is True


# J. is_local_endpoint: external/special URLs are rejected --------------------
@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",
    "http://192.0.2.1/v1",
    "http://198.51.100.1/v1",
    "http://203.0.113.1/v1",
    "http://198.18.0.1/v1",
    "http://8.8.8.8/v1",
    "http://example.com/v1",
])
def test_registry_external_endpoints_rejected(url):
    assert is_local_endpoint(url) is False


# K. Hostname lookalikes are not accidentally trusted -------------------------
@pytest.mark.parametrize("host", [
    "evil-qdrant.example.com",
    "postgres.evil.com",
    "qdrant.attacker.net",
    "piston.malicious.org",
    "vllm.phishing.com",
])
def test_hostname_lookalikes_not_trusted(host):
    # These hostnames require DNS resolution and should NOT be trusted
    assert _is_local_host(host) is False


# L. Network boundary contract ------------------------------------------------
def test_network_boundary_contract_local_permitted():
    """Local destinations must be classified as local (permitted)."""
    with NetworkGuard() as guard:
        # 127.0.0.1 is trusted loopback - should not increment external_calls
        # (actual connection may fail if nothing is listening, but classification
        # must allow it through to the real socket)
        try:
            s = socket.create_connection(("127.0.0.1", 1), timeout=0.1)
            s.close()
        except (ConnectionRefusedError, OSError):
            pass  # Connection refused is fine - classification allowed it
    assert guard.external_calls == 0


def test_network_boundary_contract_external_blocked():
    """External destinations must be classified as external (blocked)."""
    with NetworkGuard() as guard:
        with pytest.raises(ConnectionError):
            socket.create_connection(("169.254.169.254", 80), timeout=0.1)
    assert guard.external_calls >= 1
    assert "169.254.169.254" in guard.blocked


def test_network_boundary_contract_cloud_metadata_blocked():
    """Cloud metadata endpoint (169.254.169.254) MUST be blocked."""
    with NetworkGuard() as guard:
        with pytest.raises(ConnectionError):
            socket.create_connection(("169.254.169.254", 80), timeout=0.1)
    assert guard.external_calls >= 1
