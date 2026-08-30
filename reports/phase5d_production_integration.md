# Phase 5D — Production Integration & Fixes

Goal: connect the existing capabilities into one coherent production path and fix
the defects that break/sabotage it. No new capabilities, no model downloads.

## Defects found and fixed

### D1 (root cause of ungrounded artifacts) — `backend/agent/nodes/retrieve.py`
In Phase 5B the "targeted full-document read" block was accidentally nested *inside*
the `if vision_tags:` block. Result: when a task produced no vision tags (e.g. the
pure-knowledge R-1001 task), `retrieved_documents` stayed empty, so ANALYZE_EVIDENCE
extracted **zero** inspection findings / vendor parts / SOP requirements, and the
downstream approval note was ungrounded (`approval_required=False` despite breaches).

Fix: moved the full-document read out of the `vision_tags` branch so it runs for
**every** planned document type; vision-grounded RAG remains an additive step.

Verified effect:
- `backend/tests/test_artifact.py`, `test_knowledge.py`, `test_artifact_content.py`,
  `test_synthesize.py` now PASS.
- `reports/agent_evaluation.md` updated: `approval_required` is now `True` (matches
  ground truth), inspection_findings = `[catalyst_hotspot, thermowell_drift, gasket_weep]`,
  vendor_parts = `[HRS-CAT-22, HRS-GSK-1001, HRS-TW-1001]`, evaluation **10/10**.

### D2 — `backend/app/storage/postgres.py` (async driver root cause)
`create_async_engine(settings.POSTGRES_URL)` with a sync `postgresql://` URL raised
`InvalidRequestError: asyncio extension requires an async driver` at **import time**,
so the entire backend failed to import.

Fix:
- `app/config.py`: default `POSTGRES_URL` → `postgresql+asyncpg://...@localhost:5432/...`
  (asyncpg is installed). Docker deploy overrides via env to the `postgres` service name
  with the `+asyncpg` driver; `QDRANT_URL` default now `http://localhost:6333`.
- `postgres.py`: engine creation wrapped so a bad config no longer crashes import; `init_db`
  degrades gracefully (logs a warning and continues offline) when Postgres is unreachable.
  Postgres is NOT removed or disabled — it is required by the `/api/documents` + `/api/executions`
  persistence path; the sovereign agent + embedded RAG simply don't need it.

### D3 (real API bug) — `backend/app/api/models.py`
`model_registry` is a `dict`, but the code called `model_registry.list_models()` /
`model_registry.get_model()` (method calls). `GET /api/models` and `GET /api/models/{id}`
raised `AttributeError`.

Fix: import and call the module-level `list_models()` / `get_model()` helpers.

### D4 — `backend/app/storage/qdrant.py`
Already degrades gracefully (catches connect errors, sets `client=None`). No change needed;
confirmed the `/api/rag` server-mode client is independent of the agent's embedded Qdrant.

## Test results (venv `sovereign-ai`, `backend/`)

```
2 failed, 40 passed, 14 skipped
```
- The **2 failures** are `test_vision.py::test_vision_server_connectivity` and
  `test_netguard.py::test_localhost_allowed_without_guard_leak` — both assert the local
  llama.cpp **vision server on :8003 is running**. They fail only because that server is
  not started in this environment (expected; they are real connectivity gates, not code bugs).
- The **14 skips** are all "server not running" skips (coder :8002 / vision :8003). They
  become live once the user starts the model servers.

## How to run the authoritative path

1. Agent (offline, embedded RAG) — already green:
   ```
   conda activate sovereign-ai
   cd backend && python -m pytest tests -q
   ```
2. Start model servers (sequentially, VRAM-limited 6 GB):
   ```
   python scripts/serve_model.py --model coder   # :8002  (2.0 GB GGUF)
   python scripts/serve_model.py --model vision  # :8003  (1.8 GB GGUF + mmproj)
   ```
   (`general` Qwen2.5-3B GGUF is NOT present — router honestly reports unavailable.)
3. Start backend:
   ```
   uvicorn app.main:app --port 8000
   ```
   Boots offline (Postgres optional via `postgresql+asyncpg://...@localhost:5432`).

## Out of scope (not touched, by design)
- `backend/app/rag/*` mock/placeholder path (dead for the agent).
- `backend/app/agents/graph.py` (dead duplicate of `backend/agent`).
- `backend/ingestion/` separate contribution (documented as unused, OPTION A).
- No model downloads, no GPU rebuild.
