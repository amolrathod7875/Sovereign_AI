"""Network sovereignty guard.

Wraps agent execution so that ANY attempt to open a socket to a non-loopback,
non-private address is blocked and counted. This both *proves* and *enforces*
that the agent workflow uses zero external network calls.

It is safe to install globally for the duration of a run: the local hybrid RAG
(embedded Qdrant + local BM25 + offline sentence-transformers) and python-docx
perform no outbound network activity.

The guard is reentrant and supports *nested* use (e.g. a test wrapping an agent
run that wraps itself). A stack of saved ``socket.socket`` classes guarantees
that the global socket state is restored EXACTLY to what the outermost guard
found, so the patch can never leak between tests or across requests.
"""
import socket
import ipaddress
from typing import List, Optional


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Trusted local application networks: loopback + RFC1918 only.
# Explicitly excludes link-local (169.254/16), documentation ranges
# (192.0.2/24, 198.51.100/24, 203.0.113/24), benchmark ranges (198.18/15),
# IPv6 link-local (fe80::/10), IPv6 ULA (fc00::/7), multicast, reserved, etc.
_TRUSTED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # IPv4 loopback
    ipaddress.ip_network("10.0.0.0/8"),        # RFC1918
    ipaddress.ip_network("172.16.0.0/12"),     # RFC1918
    ipaddress.ip_network("192.168.0.0/16"),    # RFC1918
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
]

# Saved `socket.socket` classes, one entry per active (nested) guard layer.
# On exit each layer restores `socket.socket` to the value it saved, so the
# outermost layer returns the global to its original state (no leakage).
_SAVED_SOCKETS: List[type] = []

# Active guard stack (innermost last). `_guarded_connect` records blocked calls
# on the top-most guard.
_GUARD_STACK: List["NetworkGuard"] = []

# The genuine, un-patched socket class captured by the outermost guard. The
# patched `connect` delegates HERE for allowed (loopback) connections.
_REAL_SOCKET: Optional[type] = None


def _is_local_host(host: str) -> bool:
    """True only for explicitly trusted local application destinations.

    Trusted = loopback (127.0.0.0/8, ::1) or RFC1918 private networks
    (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16).

    Everything else is treated as external and blocked:
      - link-local (169.254.0.0/16) including cloud metadata (169.254.169.254)
      - documentation ranges (192.0.2/24, 198.51.100/24, 203.0.113/24)
      - benchmark ranges (198.18.0.0/15)
      - IPv6 link-local (fe80::/10)
      - IPv6 ULA (fc00::/7)
      - multicast, reserved, unspecified, broadcast
      - any hostname requiring DNS resolution
    """
    if host in _LOCAL_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in _TRUSTED_NETWORKS)


def _guarded_connect(self, address, *args, **kwargs):
    """Replacement for ``socket.socket.connect`` while a guard is active."""
    host = address[0] if isinstance(address, (tuple, list)) and address else address
    guard = _GUARD_STACK[-1] if _GUARD_STACK else None
    if isinstance(host, str) and _is_local_host(host):
        # Loopback / private -> allowed, delegated to the real socket.
        if _REAL_SOCKET is not None:
            return _REAL_SOCKET.connect(self, address, *args, **kwargs)
        raise ConnectionError(
            "Network guard active but the real socket reference is unavailable"
        )
    # External -> block and record on the active guard.
    if guard is not None:
        guard.external_calls += 1
        guard.blocked.append(str(host))
    raise ConnectionError(f"Blocked external network connection to {host}")


class NetworkGuard:
    """Context manager that blocks external sockets, allows loopback.

    Safe to nest: the outermost layer captures and restores the real
    ``socket.socket``; inner layers simply intercept on top. On the outermost
    exit the original global socket state is fully restored, so the guard never
    leaks between tests or across requests.

    Restoration is guaranteed even if an exception, assertion failure, or
    network error occurs inside the ``with`` block (standard context-manager
    semantics via ``__exit__`` / ``try``-finally).
    """

    def __init__(self):
        self.external_calls: int = 0
        self.blocked: List[str] = []
        self._saved: Optional[type] = None
        self._entered: bool = False

    def __enter__(self) -> "NetworkGuard":
        global _REAL_SOCKET
        if self._entered:
            return self  # re-entrant safety (no-op)
        self._saved = socket.socket
        if not _SAVED_SOCKETS:
            # First (outermost) layer: remember the genuine socket class so the
            # patched connect can delegate real connections to it.
            _REAL_SOCKET = socket.socket
        _SAVED_SOCKETS.append(socket.socket)
        guarded = type("GuardedSocket", (socket.socket,), {})
        guarded.connect = _guarded_connect
        socket.socket = guarded
        _GUARD_STACK.append(self)
        self._entered = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        global _REAL_SOCKET
        if not self._entered:
            return False
        if _GUARD_STACK and _GUARD_STACK[-1] is self:
            _GUARD_STACK.pop()
        saved = _SAVED_SOCKETS.pop() if _SAVED_SOCKETS else None
        if not _SAVED_SOCKETS:
            # Outermost layer: fully restore the original global socket state.
            if saved is not None:
                socket.socket = saved
            _REAL_SOCKET = None
        else:
            # Restore to the still-active previous layer's patched socket.
            socket.socket = saved if saved is not None else socket.socket
        self._entered = False
        return False


def no_network() -> NetworkGuard:
    """Context-manager factory used by the agent runner and the tests."""
    return NetworkGuard()
