"""Phase 12.3B1 — Global GPU Admission Controller Tests.

Tests the cross-process file lock and model-server admission behaviour without
requiring a GPU, model weights, or running model servers.
"""
from __future__ import annotations

import asyncio
import multiprocessing
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend package root is importable.
BACKEND = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.gpu_admission import (
    GPUAdmissionLease,
    GPUAdmissionTimeout,
    acquire,
    _lock_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_ms(start: float) -> float:
    return (time.monotonic() - start) * 1000.0


def _child_hold_lock(lock_path: str, hold_s: float, ready_queue):
    """Child process target: acquire lock, signal ready, hold, release."""
    try:
        with acquire(timeout_s=30.0, lock_path=lock_path) as lease:
            ready_queue.put(True)
            time.sleep(hold_s)
    except Exception:
        ready_queue.put(False)


def _child_try_acquire(lock_path: str, timeout_s: float, result_queue):
    """Child process target: try to acquire lock, report success/failure."""
    try:
        with acquire(timeout_s=timeout_s, lock_path=lock_path) as lease:
            result_queue.put(("acquired", lease.wait_ms))
    except GPUAdmissionTimeout as e:
        result_queue.put(("timeout", str(e)))


def _child_try_acquire_during_inference(lock_path: str, timeout_s: float, result_queue):
    """Child process target used by test_lock_held_until_inference_finishes."""
    try:
        with acquire(timeout_s=timeout_s, lock_path=lock_path) as lease:
            result_queue.put(("acquired", lease.wait_ms))
    except GPUAdmissionTimeout as e:
        result_queue.put(("timeout", str(e)))


# ---------------------------------------------------------------------------
# 1. First process acquires global lock successfully
# ---------------------------------------------------------------------------
def test_first_process_acquires_lock(tmp_path):
    lock_path = str(tmp_path / "test_gpu.lock")
    with acquire(timeout_s=5.0, lock_path=lock_path) as lease:
        assert lease.wait_ms >= 0.0
        assert not lease._released


# ---------------------------------------------------------------------------
# 2. Second different process cannot acquire while first holds it
# ---------------------------------------------------------------------------
def test_second_process_blocks_while_first_holds(tmp_path):
    lock_path = str(tmp_path / "test_gpu.lock")
    ready_queue = multiprocessing.Queue()
    result_queue = multiprocessing.Queue()

    holder = multiprocessing.Process(
        target=_child_hold_lock, args=(lock_path, 3.0, ready_queue)
    )
    waiter = multiprocessing.Process(
        target=_child_try_acquire, args=(lock_path, 0.5, result_queue)
    )

    holder.start()
    waiter.start()

    assert ready_queue.get(timeout=5.0) is True
    outcome = result_queue.get(timeout=5.0)

    holder.join(timeout=5.0)
    waiter.join(timeout=5.0)

    assert not holder.is_alive()
    assert not waiter.is_alive()
    assert outcome[0] == "timeout"


# ---------------------------------------------------------------------------
# 3. After first process releases, second process can acquire
# ---------------------------------------------------------------------------
def test_second_process_acquires_after_release(tmp_path):
    lock_path = str(tmp_path / "test_gpu.lock")
    ready_queue = multiprocessing.Queue()
    result_queue = multiprocessing.Queue()

    holder = multiprocessing.Process(
        target=_child_hold_lock, args=(lock_path, 0.3, ready_queue)
    )
    waiter = multiprocessing.Process(
        target=_child_try_acquire, args=(lock_path, 5.0, result_queue)
    )

    holder.start()
    waiter.start()

    assert ready_queue.get(timeout=5.0) is True
    holder.join(timeout=5.0)
    assert not holder.is_alive()

    outcome = result_queue.get(timeout=5.0)
    waiter.join(timeout=5.0)
    assert not waiter.is_alive()
    assert outcome[0] == "acquired"


# ---------------------------------------------------------------------------
# 4. Lock releases after exception inside context
# ---------------------------------------------------------------------------
def test_lock_releases_after_exception(tmp_path):
    lock_path = str(tmp_path / "test_gpu.lock")
    try:
        with acquire(timeout_s=5.0, lock_path=lock_path) as lease:
            raise RuntimeError("inference boom")
    except RuntimeError:
        pass

    # A second acquirer must succeed immediately.
    with acquire(timeout_s=5.0, lock_path=lock_path) as lease:
        assert lease.wait_ms < 500.0


# ---------------------------------------------------------------------------
# 5. Admission timeout is bounded
# ---------------------------------------------------------------------------
def test_admission_timeout_is_bounded(tmp_path):
    lock_path = str(tmp_path / "test_gpu.lock")
    ready_queue = multiprocessing.Queue()
    result_queue = multiprocessing.Queue()

    holder = multiprocessing.Process(
        target=_child_hold_lock, args=(lock_path, 10.0, ready_queue)
    )
    waiter = multiprocessing.Process(
        target=_child_try_acquire, args=(lock_path, 0.3, result_queue)
    )

    holder.start()
    waiter.start()

    assert ready_queue.get(timeout=5.0) is True
    start = time.monotonic()
    outcome = result_queue.get(timeout=5.0)
    elapsed = time.monotonic() - start

    holder.join(timeout=5.0)
    waiter.join(timeout=5.0)

    assert outcome[0] == "timeout"
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# 6. Two successful acquisitions are serialized
# ---------------------------------------------------------------------------
def test_two_acquisitions_serialized(tmp_path):
    lock_path = str(tmp_path / "test_gpu.lock")
    results = []

    with acquire(timeout_s=5.0, lock_path=lock_path):
        results.append(time.monotonic())

    time.sleep(0.05)

    with acquire(timeout_s=5.0, lock_path=lock_path):
        results.append(time.monotonic())

    assert len(results) == 2
    assert results[1] > results[0]


# ---------------------------------------------------------------------------
# 7. Different lock paths do not interfere
# ---------------------------------------------------------------------------
def test_different_lock_paths_independent(tmp_path):
    lock_a = str(tmp_path / "a.lock")
    lock_b = str(tmp_path / "b.lock")

    with acquire(timeout_s=5.0, lock_path=lock_a):
        with acquire(timeout_s=5.0, lock_path=lock_b) as lease_b:
            assert lease_b.wait_ms < 500.0


# ---------------------------------------------------------------------------
# 7a. Same-process threads serialize on the OS lock (Windows msvcrt.locking
#     safety check)
# ---------------------------------------------------------------------------
def test_same_process_threads_serialize(tmp_path):
    lock_path = str(tmp_path / "thread_gpu.lock")
    order = []

    def holder():
        with acquire(timeout_s=5.0, lock_path=lock_path) as lease:
            order.append(("holder_in", lease.wait_ms))
            time.sleep(0.4)
            order.append("holder_out")

    def waiter():
        with acquire(timeout_s=5.0, lock_path=lock_path) as lease:
            order.append(("waiter_in", lease.wait_ms))
            order.append("waiter_out")

    t_holder = threading.Thread(target=holder)
    t_waiter = threading.Thread(target=waiter)

    t_holder.start()
    time.sleep(0.05)
    t_waiter.start()

    t_holder.join(timeout=5.0)
    t_waiter.join(timeout=5.0)

    assert not t_holder.is_alive()
    assert not t_waiter.is_alive()

    holder_in_idx = next(i for i, v in enumerate(order) if isinstance(v, tuple) and v[0] == "holder_in")
    holder_out_idx = next(i for i, v in enumerate(order) if v == "holder_out")
    waiter_in_idx = next(i for i, v in enumerate(order) if isinstance(v, tuple) and v[0] == "waiter_in")
    waiter_out_idx = next(i for i, v in enumerate(order) if v == "waiter_out")

    assert holder_in_idx < waiter_in_idx, "holder and waiter entered lock simultaneously"
    assert waiter_in_idx > holder_out_idx, "waiter entered before holder released"


# ---------------------------------------------------------------------------
# 8. Model server returns 429 when admission cannot be obtained
# ---------------------------------------------------------------------------
def test_model_server_returns_429_on_admission_failure():
    from fastapi.testclient import TestClient
    from scripts.serve_model import build_app

    mock_llm = MagicMock()
    app = build_app("qwen-coder", mock_llm, admission_timeout=0.1)
    client = TestClient(app)

    with patch("scripts.serve_model.acquire") as mock_acquire:
        mock_acquire.side_effect = GPUAdmissionTimeout("busy")
        response = client.post(
            "/v1/chat/completions",
            json={"model": "qwen-coder", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 429
    body = response.json()
    assert body["error"]["type"] == "gpu_busy"
    assert response.headers.get("Retry-After") == "5"


# ---------------------------------------------------------------------------
# 9. Fake inference runs only after admission is granted
# ---------------------------------------------------------------------------
def test_inference_runs_only_after_admission():
    from fastapi.testclient import TestClient
    from scripts.serve_model import build_app

    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {},
    }
    app = build_app("qwen-coder", mock_llm, admission_timeout=5.0)
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "qwen-coder", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 200
    assert mock_llm.create_chat_completion.called


# ---------------------------------------------------------------------------
# 10. Lock remains held until fake inference function finishes
# ---------------------------------------------------------------------------
def test_lock_held_until_inference_finishes(tmp_path):
    lock_path = str(tmp_path / "test_gpu.lock")
    inference_done = False

    def fake_inference():
        nonlocal inference_done
        time.sleep(0.2)
        inference_done = True
        return {"ok": True}

    with acquire(timeout_s=5.0, lock_path=lock_path) as lease:
        result_queue = multiprocessing.Queue()

        p = multiprocessing.Process(
            target=_child_try_acquire_during_inference,
            args=(lock_path, 0.3, result_queue),
        )
        p.start()
        outcome = result_queue.get(timeout=5.0)
        p.join(timeout=5.0)
        assert outcome[0] == "timeout"

        _ = fake_inference()

    assert inference_done


# ---------------------------------------------------------------------------
# 11. Fake inference exception still releases lock
# ---------------------------------------------------------------------------
def test_exception_during_inference_releases_lock(tmp_path):
    lock_path = str(tmp_path / "test_gpu.lock")

    def failing_inference():
        raise RuntimeError("boom")

    try:
        with acquire(timeout_s=5.0, lock_path=lock_path) as lease:
            failing_inference()
    except RuntimeError:
        pass

    with acquire(timeout_s=5.0, lock_path=lock_path) as lease:
        assert lease.wait_ms < 500.0


# ---------------------------------------------------------------------------
# 12. /v1/models continues to function with no GPU required
# ---------------------------------------------------------------------------
def test_models_endpoint_works_without_gpu():
    from fastapi.testclient import TestClient
    from scripts.serve_model import build_app

    mock_llm = MagicMock()
    app = build_app("qwen-vision", mock_llm, admission_timeout=5.0)
    client = TestClient(app)

    response = client.get("/v1/models")
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "qwen-vision"


# ---------------------------------------------------------------------------
# 13. /v1/models stays responsive while another request waits for admission
# ---------------------------------------------------------------------------
def test_models_endpoint_responsive_during_admission_wait(tmp_path):
    from fastapi.testclient import TestClient
    from scripts.serve_model import build_app

    lock_path = str(tmp_path / "test_gpu.lock")
    mock_llm = MagicMock()
    app = build_app("qwen-coder", mock_llm, admission_timeout=5.0)
    client = TestClient(app)

    ready_queue = multiprocessing.Queue()
    holder = multiprocessing.Process(
        target=_child_hold_lock, args=(lock_path, 2.0, ready_queue)
    )
    holder.start()
    assert ready_queue.get(timeout=5.0) is True

    start = time.monotonic()
    response = client.get("/v1/models")
    elapsed_ms = (time.monotonic() - start) * 1000.0

    assert response.status_code == 200
    assert elapsed_ms < 1000.0

    holder.join(timeout=5.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
