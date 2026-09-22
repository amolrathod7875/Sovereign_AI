"""Cross-process GPU admission lock for local inference.

Uses OS file locks so that separate model-server processes serialize access to
the single host GPU.  No cloud dependency, no nvidia-smi polling.

Lock path resolution order:
  1. ``SOVEREIGN_GPU_LOCK_PATH`` environment variable
  2. ``tempfile.gettempdir() / "sovereign_ai_gpu.lock"``

Windows: ``msvcrt.locking`` on a persistent file handle.
POSIX:   ``fcntl.flock`` on a persistent file handle.

The file itself is not the lock; the OS file-handle lock is authoritative.
Do not delete the file between requests.  If the owning process crashes the
OS releases the lock automatically when the handle is closed.
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Optional


class GPUAdmissionTimeout(Exception):
    """Raised when the global GPU slot cannot be acquired within the timeout."""


class GPUAdmissionLease:
    """Opaque handle returned by :func:`acquire`.  Holds the OS file lock."""

    def __init__(self, lock_path: str, fd: int, wait_ms: float) -> None:
        self._lock_path = lock_path
        self._fd = fd
        self._wait_ms = wait_ms
        self._released = False

    @property
    def wait_ms(self) -> float:
        return self._wait_ms

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        try:
            _release_file_lock(self._fd)
        except Exception:
            pass
        try:
            os.close(self._fd)
        except Exception:
            pass

    def __enter__(self) -> "GPUAdmissionLease":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


def _lock_path() -> str:
    env_path = os.environ.get("SOVEREIGN_GPU_LOCK_PATH")
    if env_path:
        return env_path
    return str(Path(tempfile.gettempdir()) / "sovereign_ai_gpu.lock")


def _ensure_lock_file(path: str) -> None:
    """Create the lock file with at least one byte if it does not exist."""
    if not os.path.exists(path):
        try:
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
            try:
                os.write(fd, b"\x00")
            except Exception:
                pass
            finally:
                os.close(fd)
        except Exception:
            pass


def _acquire_file_lock(fd: int, timeout_s: float) -> bool:
    """Attempt an exclusive file lock.  Returns True on success."""
    if os.name == "nt":
        import msvcrt

        start = time.monotonic()
        sleep_s = 0.05
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                elapsed = time.monotonic() - start
                if elapsed >= timeout_s:
                    return False
                time.sleep(sleep_s)
    else:
        import fcntl

        start = time.monotonic()
        sleep_s = 0.05
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (IOError, OSError):
                elapsed = time.monotonic() - start
                if elapsed >= timeout_s:
                    return False
                time.sleep(sleep_s)


def _release_file_lock(fd: int) -> None:
    """Release the file lock."""
    if os.name == "nt":
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except (IOError, OSError):
            pass


def acquire(timeout_s: float = 60.0, lock_path: Optional[str] = None) -> GPUAdmissionLease:
    """Acquire the global GPU admission lease.

    Blocks until the lock is acquired or *timeout_s* elapses.
    """
    path = lock_path or _lock_path()
    _ensure_lock_file(path)
    fd = os.open(path, os.O_RDWR)
    try:
        start = time.monotonic()
        if not _acquire_file_lock(fd, timeout_s):
            wait_ms = (time.monotonic() - start) * 1000.0
            os.close(fd)
            raise GPUAdmissionTimeout(
                f"GPU admission timed out after {timeout_s:.1f}s (waited {wait_ms:.0f}ms)"
            )
        wait_ms = (time.monotonic() - start) * 1000.0
        return GPUAdmissionLease(path, fd, wait_ms)
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        raise
