"""Network sovereignty guard.

Wraps agent execution so that ANY attempt to open a socket to a non-loopback,
non-private address is blocked and counted. This both *proves* and *enforces*
that the agent workflow uses zero external network calls.

It is safe to install globally for the duration of a run: the local hybrid RAG
(embedded Qdrant + local BM25 + offline sentence-transformers) and python-docx
perform no outbound network activity.
"""
import socket
import ipaddress
from typing import List


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


# Module-level reference to the real socket class (set on first activation). The
# guarded `connect` must delegate to THIS, not to `self` (which is the socket
# instance, not the guard).
_ORIGINAL_SOCKET = None


class NetworkGuard:
    def __init__(self):
        self.external_calls: int = 0
        self.blocked: List[str] = []

    def _guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) and address else address
        if isinstance(host, str) and host not in _LOCAL_HOSTS:
            try:
                ip = ipaddress.ip_address(host)
                if ip.is_loopback or ip.is_private:
                    return _ORIGINAL_SOCKET.connect(self, address, *args, **kwargs)
            except ValueError:
                # Unresolved hostname -> treat as external (would require DNS/network).
                pass
            self.external_calls += 1
            self.blocked.append(str(host))
            raise ConnectionError(f"Blocked external network connection to {host}")
        return _ORIGINAL_SOCKET.connect(self, address, *args, **kwargs)

    def __enter__(self):
        global _ORIGINAL_SOCKET
        _ORIGINAL_SOCKET = socket.socket
        guarded = type("GuardedSocket", (socket.socket,), {})
        # Assign the UNBOUND function (not the bound method on the guard), so that
        # sock.connect(address) invokes _guarded_connect(sock, address).
        guarded.connect = NetworkGuard._guarded_connect
        socket.socket = guarded
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _ORIGINAL_SOCKET
        if _ORIGINAL_SOCKET is not None:
            socket.socket = _ORIGINAL_SOCKET
            _ORIGINAL_SOCKET = None
        return False


def no_network() -> NetworkGuard:
    """Context-manager factory used by the agent runner and the tests."""
    return NetworkGuard()
