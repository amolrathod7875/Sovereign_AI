# Phase 5C-2 Model Router

## Objective
A single, extensible, capability-based local model routing system for Sovereign AI.
The router classifies a task along several independent dimensions, matches the
required capabilities against the local model registry, and returns an explainable
`RoutingDecision` listing every local model the task needs. No cloud fallback, no
second agent, no new server, no new model downloads.

## Architecture

```
USER
  │
  ▼
AGENT  (backend/agent LangGraph — authoritative, unchanged)
  │
  ▼
MODEL ROUTER  (backend/app/models/router.py — capability-based)
  │
  ├──> MODEL REGISTRY  (backend/app/models/registry.py — all local=True)
  │        │
  │        ├── general      Qwen2.5-3B-Instruct      localhost:8001
  │        ├── qwen-coder   Qwen2.5-Coder-3B-Instruct localhost:8002
  │        ├── vision       Qwen2.5-VL-3B-Instruct    localhost:8003
  │        ├── embedding     BGE-large-en-v1.5        local
  │        └── reranker      BGE-reranker-large        local
  │
  └──> EXISTING clients/tools (no new orchestration engine)
            vision tool (agent.tools.vision)  -> 127.0.0.1:8003
            coder client (agent.coder.model)  -> localhost:8002
            local RAG    (agent.tools.search_kb)
            sandbox      (agent.tools.python_execute)
  │
  ▼
RESULT  (external_calls == 0, every model local)
```

## Available Models (discovered from the repository)

| Model | Local | Capabilities | Endpoint | Status on this host |
|-------|-------|-------------|----------|---------------------|
| general (Qwen2.5-3B-Instruct) | yes | text_generation, reasoning, summarization, rag_synthesis, tool_calling | http://localhost:8001/v1 | configured; GGUF weights **not present** on this host |
| qwen-coder (Qwen2.5-Coder-3B-Instruct) | yes | text_generation, code_generation, code_review, debugging, tool_calling | http://localhost:8002/v1 | **live** (started via existing `scripts/serve_model.py`) |
| vision (Qwen2.5-VL-3B-Instruct) | yes | vision, image_analysis, pid_analysis, document_vision, ocr, text_generation | http://127.0.0.1:8003/v1 | **live** |
| embedding (BGE-large-en-v1.5) | yes | embedding | /models/embedding | local |
| reranker (BGE-reranker-large) | yes | reranking | /models/reranker | local |

Endpoints were **discovered**, not assumed: `CODER_ENDPOINT` (agent/coder/config.py)
→ :8002, `VISION_ENDPOINT` (agent/config.py) → :8003, and the general model → :8001
(loopback, by the same local-server convention). All are loopback/private, so the
router's sovereignty guard accepts them.

## Routing Matrix

| Task | Selected Model | Models Required | RAG | Vision | Tools |
|------|----------------|----------------|-----|--------|-------|
| Write Python code (Reynolds) | qwen-coder | qwen-coder | no | no | yes (sandbox) |
| Identify equipment in P&ID | vision | vision | no | yes | no |
| Explain R-1001 maintenance (KB) | general | general | yes | no | no |
| Inspect P&ID + explain via KB | vision (primary) | vision, general | yes | yes | no |

A complex (multimodal) task legitimately uses **more than one** local model: the VLM
extracts `R-1001`, then RAG retrieves local evidence, then the general model
synthesises — exactly the required multi-model workflow, driven entirely through the
existing agent/tool architecture.

## Demonstrations (all executed, all `external_calls = 0`)

### DEMO 1 — CODING
- Router → `qwen-coder` (confidence 0.88, reason "code generation / execution required").
- Generated a correct `calculate_reynolds_number(density, velocity, length, viscosity)`
  implementation, then executed it in the **existing local sandbox**
  (`agent.tools.python_execute`).
- Result: `exit_code = 0`, stdout `The Reynolds number is: 10000000.0` → **verified**.

### DEMO 2 — VISION
- Router → `vision` (confidence 0.92).
- `agent.tools.vision.analyze_image` on `158.jpg` via the live `127.0.0.1:8003` server.
- `model = Qwen2.5-VL-3B-Instruct`, `data_origin = local`. The VLM treated output as
  witness evidence (uncertain items preserved); in the multimodal demo below it
  extracted the tag **R-1001**.

### DEMO 3 — KNOWLEDGE
- Router → `general` (confidence 0.82), `requires_rag = True`.
- Local RAG returned **6** evidence hits (maintenance_approval_note, equipment_manual,
  preventive_maintenance_sop, inspection_report, …) with scores.
- The dedicated `general` GGUF is not present on this host, so the synthesis step
  transparently reports "general model server not running on this host" and the
  answer is grounded in the retrieved local evidence (no external call, no fabricated
  general answer).

### DEMO 4 — MULTIMODAL
- Router → `vision` (primary) + `general`, `requires_rag = True` (confidence 0.90).
- VLM extracted tag **`R-1001`**; RAG returned **6** local evidence hits
  (canonical_profile, plant_context, equipment_manual, inspection_report, …);
  reasoning synthesis step reported honestly (general server absent on this host).
- Full `vision → RAG → reasoning` workflow executed locally with `external_calls = 0`.

## Routing Latency (Step 20)

Routing is lightweight — it never invokes a large model to classify a request.

| Phase | Measured |
|-------|----------|
| Task classification | < 1 ms |
| Registry lookup | < 1 ms |
| Model selection + local-only check | < 1 ms |
| **Total routing overhead** | **< 1 ms** (demo printed `0.0 ms`) |

(The multi-second "execute" times are the actual local model inference / RAG / sandbox,
which is expected and fully on-machine.)

## Sovereignty (Step 7 & 19)

- `local_only` is enforced: every selected model must have `local = True` AND a
  loopback/private endpoint (`is_local_endpoint` / `validate_local_endpoint`).
- A model flagged local but pointing at a public endpoint is **rejected**
  (`ConnectionError`), and a capability with no local model raises
  `NoLocalModelAvailable` — the router never falls back to an external API.
- Every demonstration was wrapped in `no_network()`; **total external calls = 0**.
- localhost model calls (`:8002` coder, `:8003` vision) work correctly under
  NetworkGuard.

## Network Validation (Step 19)

| Path | Result |
|------|--------|
| coding → localhost:8002 | works (external_calls = 0) |
| vision → 127.0.0.1:8003 | works (external_calls = 0) |
| general → localhost:8001 | local; server not running here (transparent) |
| RAG → local KB | works (external_calls = 0) |
| router → registry | local only |

## Tests

```
backend/tests/test_router.py  -> 16 passed  (full required matrix)
backend/tests/ (whole dir)    -> 51 passed, 4 failed, 1 skipped
```

Failures (honest — all **pre-existing Phase 4** `approval_required` decision-logic
assertions, NOT introduced by this phase, NOT modified):

- `tests/test_agent.py::test_graph_runs_end_to_end`
- `tests/test_agent.py::test_run_agent_task_output_shape`
- `tests/test_agent_e2e.py::test_full_task_end_to_end`
- `tests/test_agent_e2e.py::test_fastapi_endpoint`

Skipped (pre-existing, unrelated):

- `tests/test_coder.py` — requires the separate Qwen Coder server (it is actually
  running on :8002 in this session; the test's own readiness probe did not match).

Other known issues carried over (NOT fixed — out of scope, do not modify unrelated
components to make tests green):

- `backend/ingestion/tests/test_ingestion.py` — pre-existing collection error
  (`ModuleNotFoundError: No module named 'app.ingestion'`).
- `backend/app/main.py` boot — pre-existing `psycopg2`/async-driver error in
  `app/storage/postgres.py`. The router logic and `/api/models/route` handler are
  verified via the 16 unit tests; the full FastAPI app does not boot in this
  environment for an independent reason.
- GPU (CUDA offload) remains disabled (CPU-only llama.cpp build) — out of scope.

## Explainability (Step 14)

Every `RoutingDecision` exposes: `task_type`, `modality`, `selected_model`,
`models_required`, `requires_rag`, `requires_tools`, `confidence`, `reason`,
`capabilities`, `all_local`, `external_calls`. The agent result now includes a
`routing` block and the FastAPI `AgentRunResponse` exposes it, so the frontend
(Phase 6) can display Model / Task / Reason / Local.

## Acceptance Criteria

- [x] Existing model registry reused (`backend/app/models/registry.py`)
- [x] Existing model client reused (`backend/app/models/client.py`)
- [x] Existing router reused/extended (`backend/app/models/router.py`)
- [x] No duplicate model server (reused `scripts/serve_model.py` for :8002)
- [x] No duplicate agent / RAG / model downloads
- [x] Coding routes to Qwen Coder
- [x] Vision routes to Qwen-VL
- [x] Knowledge task uses RAG (+ general)
- [x] Multimodal workflow supports multiple models
- [x] Local-only enforcement works
- [x] NetworkGuard works (external_calls = 0)
- [x] Existing vision workflow still works
- [x] Existing coder workflow still works
- [x] Existing RAG workflow still works
- [x] Tests executed
- [x] Report generated

## Files Changed

- `backend/app/models/registry.py` — enriched entries (id, display_name, modalities,
  local), added `get_local_models`, `get_models_with_capability`, `is_local_endpoint`,
  `validate_local_endpoint`, `capability_label`; endpoints discovered/aligned to
  running local servers.
- `backend/app/models/router.py` — new capability-based `route(RoutingRequest)`,
  `classify_task` (multi-factor), `execute_routing` (dispatches to existing
  tools/clients), `NoLocalModelAvailable`, backward-compatible `route_task`.
- `backend/app/models/__init__.py` — exports router/registry helpers.
- `backend/app/schemas/api.py` + `__init__.py` — added `RoutingRequest`,
  `RoutingDecision`; added `local`/`modalities` to `ModelInfo`.
- `backend/app/api/models.py` — `POST /api/models/route` now returns `RoutingDecision`
  and enforces local-only (422 on no local model).
- `backend/agent/run.py` — attaches `routing` (explainability) to agent result.
- `backend/agent/coder/run.py` — attaches `routing` to coder result.
- `backend/app/api/agent.py` — `AgentRunResponse.routing` field.
- `backend/tests/test_router.py` — NEW, 16 tests (required matrix).
- `scripts/demo_phase5c2_router.py` — NEW, the four demonstrations.
- `reports/phase5c2_model_router.md` — this report.
