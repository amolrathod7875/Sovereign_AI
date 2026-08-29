# Phase 5C-1.5 NetGuard Stabilization

## Root Cause

The NetworkGuard used a **single module-global** (`_ORIGINAL_SOCKET`) to remember the
real `socket.socket` class and to delegate allowed connections back to it. Two defects
compounded:

1. **Nested-guard global corruption (the leak).** `NetworkGuard` was used *nested*:
   `test_agent_completes_under_netguard` wraps `run_agent_task`, and `run_agent_task`
   also wraps itself in `no_network()`. On the *inner* `__enter__`, `_ORIGINAL_SOCKET`
   was overwritten with the outer layer's patched `GuardedSocket`. On the *inner*
   `__exit__`, `_ORIGINAL_SOCKET` was set to `None`. The *outer* `__exit__` then saw
   `_ORIGINAL_SOCKET is None`, took its `if` branch as false, and **never restored
   `socket.socket`** — leaving it permanently patched to `GuardedSocket`. Worse, the
   patched `connect` delegated to the now-`None` `_ORIGINAL_SOCKET`, so even legitimate
   localhost connections then raised `AttributeError: None.connect`. This is why vision
   tests failed *only when run after* an agent/NetGuard test.

2. **Wrong counting target.** `_guarded_connect` was attached to the `GuardedSocket`
   class, so `self` inside it was the **socket instance**, not the `NetworkGuard`.
   `self.external_calls += 1` therefore incremented a counter on throwaway socket objects
   while `guard.external_calls` stayed `0` — so `test_netguard_blocks_external_connections`
   asserted `0 >= 1` and failed.

## Fix

Rewrote `backend/agent/security/netguard.py`:

- Replaced the single global with a **stack** (`_SAVED_SOCKETS`) and an active-guard
  stack (`_GUARD_STACK`). Each layer saves the `socket.socket` it found and pushes the
  patched class. On exit it pops and restores *that exact value*; only when the stack
  empties is the global `socket.socket` returned to the original class and
  `_REAL_SOCKET` cleared. Nested guards (test + `run_agent_task`) now restore perfectly.
- Counting now targets the **active `NetworkGuard`** (`_GUARD_STACK[-1]`), so blocked
  external attempts are recorded on the correct object.
- The patched `connect` delegates allowed (loopback/private) connections to the genuine
  socket captured by the outermost layer (`_REAL_SOCKET`), and blocks + records everything
  else (`8.8.8.8`, `example.com`, unresolved hostnames).
- Restoration is guaranteed via normal context-manager `__exit__` semantics (exception /
  assertion / network error inside the block all trigger it). A re-entrancy guard prevents
  double-patching the same instance.

No other module was changed. The existing `no_network()` factory and `NetworkGuard` API
are unchanged, so `agent.run`, `agent.coder.run`, `demo_*.py`, and all tests keep working.

## External Network

Blocked: **PASS**
- `socket.create_connection(("8.8.8.8", 53))` → blocked; `example.com:80` → blocked;
  unresolved hostname → blocked. `guard.external_calls >= 1`, `guard.blocked` populated.

## Localhost

`127.0.0.1:8003` allowed: **PASS**
- Under an active guard, `socket.create_connection(("127.0.0.1", 8003))` succeeds and
  `guard.external_calls == 0`. The real Qwen-VL llama.cpp server on `:8003` is reachable
  while the guard is active.

## Restoration

Original socket state restored: **PASS**
- After a single context (`test_socket_restored_after_context`), after an exception inside
  the block (`test_socket_restored_after_exception`), after 3 sequential contexts
  (`test_multiple_sequential_contexts`), and after nested contexts (`run_agent_task` inside
  a test guard), `socket.socket is <original>` holds. The leak that broke later vision tests
  is gone.

## Test Order Independence

| Scenario | Result |
|----------|--------|
| Agent → Vision | **PASS** (all 10 vision tests pass after agent e2e) |
| Vision → Agent | **PASS** (order no longer changes outcomes) |
| NetworkGuard → Vision | **PASS** |
| Vision → NetworkGuard | **PASS** |

Verified by running:
- `pytest tests/test_agent_e2e.py tests/test_vision.py` → 14 passed, 2 failed (pre-existing)
- `pytest tests/test_vision.py tests/test_agent_e2e.py` → 14 passed, 2 failed (identical)
- `pytest tests/test_vision.py` → 10 passed
- `pytest tests/test_agent_e2e.py` → 4 passed, 2 failed (pre-existing)
- `pytest tests/` → 35 passed, 4 failed, 1 skipped

The 4 remaining failures are **identical in every order** and are the pre-existing
Phase 4 `approval_required is True` decision-logic assertions (see Regression below) —
they are unrelated to NetGuard and were deliberately left untouched per phase scope.

## End-to-End

158.jpg:
- **PASS** — `analyze_image` / `analyze_pid` return the canonical schema via the live
  `:8003` server.

Vision → RAG:
- **PASS** — `test_vision_tags_drive_rag_retrieval` and `test_vision_tags_drive_rag_retrieval`
  extract equipment tags (incl. `R-1001`) and return local RAG evidence.

Vision → Agent:
- **PASS** — `test_agent_invokes_vision_tool` and `test_end_to_end_multimodal_task` run the
  full graph with `status == "VERIFIED"`, `vision_evidence` populated, `external_calls == 0`.

## Network Sovereignty

External calls during the real agent run: **0**
- Every `run_agent_task` invocation (text-only and multimodal) reports
  `external_calls == 0`. Localhost model communication to `127.0.0.1:8003` is allowed and is
  **not** counted as an external call. External destinations are blocked and recorded.

## Regression

Pre-existing failures that remain (NOT introduced by this phase, NOT NetGuard-related):

1. `tests/test_agent.py::test_graph_runs_end_to_end` — `assert final["decision"]["approval_required"] is True`
2. `tests/test_agent.py::test_run_agent_task_output_shape` — `assert res["approval_required"] is True`
3. `tests/test_agent_e2e.py::test_full_task_end_to_end` — `assert res["approval_required"] is True`
4. `tests/test_agent_e2e.py::test_fastapi_endpoint` — `assert body["approval_required"] is True`

These are Phase 4 agent decision-logic assertions (the agent currently resolves
`approval_required = False` for the R-1001 task). They fail identically regardless of test
order and are outside the NetGuard scope of this phase; per instructions they are documented,
not rewritten.

Additional pre-existing, unrelated notes:
- `backend/ingestion/tests/test_ingestion.py` has a **collection error** importing a
  non-existent `app.ingestion` module. Untouched (ingestion is out of scope this phase).
- `tests/test_coder.py` is **skipped** (needs the separate Qwen Coder server, not running).
- GPU (CUDA offload) remains disabled — CPU Qwen-VL on `:8003` is unchanged and working
  (out of scope per phase instructions).

## Files Changed

- `backend/agent/security/netguard.py` — root-cause fix (stack-based restore + correct
  external-call counting). No API change.
- `backend/tests/test_netguard.py` — NEW: scenarios A–J (external blocked, localhost allowed,
  `:8003` allowed, restored after context, restored after exception, sequential contexts,
  NetGuard→vision, vision→NetGuard, agent→vision, vision→agent, endpoint guard).

No changes to the agent graph, RAG, vision tool internals, model routing, frontend, or
ingestion.

## Confirmation

`socket.socket` is fully restored to its original class after every `NetworkGuard` context,
including nested ones and exception paths. The NetGuard-induced vision connection failures
that appeared when agent tests ran before vision tests are **eliminated**; test results no
longer depend on execution order.
