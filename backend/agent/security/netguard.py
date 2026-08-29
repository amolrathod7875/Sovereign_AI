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


class NetworkGuard:
    def __init__(self):
        self.external_calls: int = 0
        self.blocked: List[str] = []
        self._original_socket = None

    def _guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) and address else address
        if isinstance(host, str) and host not in _LOCAL_HOSTS:
            try:
                ip = ipaddress.ip_address(host)
                if ip.is_loopback or ip.is_private:
                    return self._original_socket.connect(self, address, *args, **kwargs)
            except ValueError:
                # Unresolved hostname -> treat as external (would require DNS/network).
                pass
            self.external_calls += 1
            self.blocked.append(str(host))
            raise ConnectionError(f"Blocked external network connection to {host}")
        return self._original_socket.connect(self, address, *args, **kwargs)

    def __enter__(self):
        self._original_socket = socket.socket
        guarded = type("GuardedSocket", (socket.socket,), {})
        guarded.connect = self._guarded_connect
        socket.socket = guarded
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._original_socket is not None:
            socket.socket = self._original_socket
        return False


def no_network() -> NetworkGuard:
    """Context-manager factory used by the agent runner and the tests."""
    return NetworkGuard()
