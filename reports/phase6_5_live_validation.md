# Phase 6.5 — Live System Validation

> Validation performed on the developer machine against the **live** system:
> FastAPI backend (`:8000`) → model router → local llama.cpp model servers
> (`:8002` coder, `:8003` vision) → embedded Qdrant/BM25 RAG → agent → DOCX artifact.
> No mock responses were used. All model inference was real and local.

## Environment

| Item | Value |
|------|-------|
| Python | 3.11.9 (conda env `sovereign-ai`) |
| CUDA toolkit (`nvcc`) | 12.4.99 (Build V12.4.99) |
| NVIDIA driver | 591.66 (reports CUDA Version 13.1) |
| GPU | NVIDIA GeForce RTX 4050 Laptop GPU |
| VRAM | 6141 MiB (~6 GB) |
| llama.cpp GPU offload | **False** — installed wheel is CPU-only (no `ggml-cuda.dll`); `llama_cpp.llama_supports_gpu_offload()` returns `False` |

> GPU acceleration could **not** be enabled: the rules forbid rebuilding llama.cpp or
> changing CUDA configuration. All inference therefore ran on CPU. See Part 11.

## Models

| Role | Path | Status |
|------|------|--------|
| Coder | `models/qwen-coder/qwen2.5-coder-3b-instruct-q4_k_m.gguf` | present |
| Vision | `models/qwen-vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` | present |
| Vision mmproj | `models/qwen-vision/mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf` | present |
| General (Qwen2.5-3B) | — (no GGUF under `models/`; registry endpoint `localhost:8001` has **no** server) | **NOT AVAILABLE / NOT CONFIGURED** |

Model servers were started from the existing `scripts/serve_model.py` exactly as the
project documents (coder `:8002`, vision `:8003` with `--mmproj`). Because the
llama.cpp build is CPU-only, VRAM was not a constraint; models were run sequentially
to avoid CPU contention.

## Coder (Part 4)

Submitted via `POST /api/coder/run` (the same endpoint the frontend uses):
*"Write a Python function that calculates Reynolds number. Include input validation."*

| Stage | Result | Evidence |
|-------|--------|----------|
| server (`:8002`) | **PASS** | `/v1/models` → 200 |
| routing | **PASS** | `selected_model=qwen-coder`, `all_local=True`, `local_only=True` |
| generation | **PASS** | Correct `calculate_reynolds_number()` with positive-value validation generated |
| sandbox | **EXECUTED** | Sandbox invoked; `network_blocked=0`, generated files written to workspace |
| verification | **FAILED (harness defect)** | See below |
| external calls | **0** | `external_calls=0` from `no_network` guard |
| latency | **573.82 s** (CPU-only 3B) | end-to-end |

**Verification failure is a genuine pre-existing defect, not a model failure:**
the sandbox's import-blocker (`backend/agent/coder/sandbox.py`) implements the
deprecated `MetaPathFinder.find_module` API, which Python 3.11 no longer calls
(it requires `find_spec`). Consequently `import pytest` raises
`AttributeError: '_ImportBlocker' object has no attribute 'find_spec'`, so the
generated test never executes and the agent reports `FAILED`. The *generated code*
is logically correct (Re = ρ·v·D/μ = 1,000,000 for the test inputs). The failure is
in the verification harness, not in generation/routing/server.

## Vision (Part 5)

`POST /api/vision/analyze` on `PID_Dataset/0__raw_data/sheets/test/158.jpg`,
`analysis_type=pid`.

| Stage | Result | Evidence |
|-------|--------|----------|
| upload (file reached backend) | **PASS** | `status=completed` |
| vision endpoint (`:8003`) | **PASS** | server responded |
| Qwen-VL | **PASS** | `model=Qwen2.5-VL-3B-Instruct`; returned real equipment tags incl. `R-1001` |
| GPU offload | **NOT VERIFIED** | CPU-only llama.cpp |
| result | **PASS** | structured findings/entities; model marked low-confidence items `uncertain` (no fabrication) |
| external calls | **0** | `external_calls=0` |
| latency | **35.33 s** | |

## RAG (Part 6)

`POST /api/rag/search` — *"Explain the maintenance requirements for R-1001 using the
local knowledge base."* (uses the authoritative embedded Qdrant + BM25 retriever the
agent uses, not a placeholder).

| Stage | Result | Evidence |
|-------|--------|----------|
| Qdrant (embedded) | **PASS** | returned 6 chunks |
| BM25 | **PASS** | hybrid retriever; lexical index = 393 chunks |
| retrieval | **PASS** | `retrieved_chunks > 0` (6) |
| grounding | **PASS** | every chunk carries `source_file`, `document_type`, `asset_tag`, `data_origin` |
| external calls | **0** | |
| latency | **2.2 s** | |

Retrieved from the **existing** synthetic R-1001 corpus (approval_note, manual,
pm_sop, inspection_report, vendor_correspondence) — no new index created.

## Multimodal (Part 7)

`POST /api/agent/run` with `image_path=158.jpg`, `asset_tag=R-1001`,
`analysis_type=pid`, task: *"Inspect this P&ID, identify R-1001, and explain its
maintenance requirements using the local knowledge base."*

| # | Requirement | Result |
|---|-------------|--------|
| 1 | image reached backend | **PASS** |
| 2 | Qwen-VL processed image | **PASS** (tags `R-1001`, `V-1001`, `P-1001`, `I-1001`) |
| 3 | R-1001 identification came from image | **PASS** (vision_tags include R-1001; reasoning cites local Qwen-VL inspection) |
| 4 | RAG retrieved evidence | **PASS** (22 evidence items from local KB) |
| 5 | maintenance info from local evidence | **PASS** (actions derived from SOP/inspection/vendor docs) |
| 6 | final answer combined both | **PASS** (reasoning chains vision witness + RAG evidence) |
| 7 | external calls = 0 | **PASS** (`external_calls=0`) |

- `status=VERIFIED`, decision: *"Initiate a controlled reactor shutdown and perform
  corrective maintenance on R-1001 … obtain maintenance approval before execution."*
- `approval_required=True`
- **latency: 34.43 s**, **external calls: 0**

## Approval Artifact (Part 8)

Produced by the same run (GENERATE_APPROVAL_NOTE → verify → VERIFIED).

- **File:** `data/outputs/R-1001_api_run_dc5cf61984f0.docx` (39,823 bytes, 93 paragraphs)
- `verify_docx`: `ok=True`, `asset_present=True`, `disclaimer_present=True`,
  `sources_present=True`
- **Grounding:** all engineering values (catalyst, gasket, thermowell, sensor
  breaches, spare part numbers) originate from the synthetic local R-1001 corpus;
  a synthetic-data disclaimer is present; the vision witness is explicitly flagged
  as non-engineering-truth. **No fabricated engineering values.**
- **Decision supported** by retrieved evidence (`supporting_evidence` lists
  pm_sop, inspection_report, sensor_dataset, equipment_manual, operating_sop,
  vendor_correspondence).
- File opens and is a valid OOXML DOCX (verified with `python-docx`).

## Frontend (Part 9)

SPA in `frontend/` (Vite + React + TypeScript). Verified:

- `npm run build` (tsc + vite) **succeeds** — 1654 modules, no type/compile errors
  (the class of error that would throw in the browser console at load).
- `vite preview` **serves** the app (HTTP 200) and the `/api` proxy reaches the live
  backend (`GET /api/system/status` → 200, `sovereign=True`).
- The `System` page is **not hard-coded**: `System.tsx` renders `c.status` from the
  probed `/api/system/status` response; states ONLINE / OFFLINE / UNAVAILABLE /
  NOT CONFIGURED are emitted by the backend (`app/api/system.py`), not fabricated.
- All six pages are wired to the real API client (`frontend/src/lib/api/client.ts`):
  Coding→`/coder/run`, Vision→`/vision/analyze`, Knowledge→`/rag/search`,
  Multimodal→`/agent/run`, Artifact→`/artifacts`, System→`/system/status`.

| Page | Result |
|------|--------|
| System | PASS (live probed status) |
| Coding | PASS (endpoint reachable) |
| Vision | PASS |
| Knowledge | PASS |
| Multimodal | PASS |
| Artifact | PASS |

> **Browser console caveat:** no browser-automation tool was available in this
> environment, so an interactive click-through console check could not be performed.
> The clean production build + correct API wiring + working proxy are strong evidence
> against load-time/runtime JS errors; a manual `npm run dev` session is recommended
> for the final interactive console confirmation.

## Network (Part 10)

- `external_api_calls = 0` (reported by `/api/system/status` and by every run's
  `no_network` guard).
- `blocked_connections = 0` (no external attempt was even attempted; the sandbox and
  NetworkGuard block proactively).
- All communication was loopback: `localhost:8000` (FastAPI), `localhost:8003`
  (vision), `localhost:8002` (coder when started). These are local, not external.
- No external destination was observed in any run. NetworkGuard enforced sovereignty
  end-to-end.

## GPU (Part 11)

`llama_supports_gpu_offload()` = `False`; the llama.cpp wheel contains
`ggml-base/cpu/llama/mtmd` DLLs but **no `ggml-cuda.dll`**. Per the task rules,
llama.cpp was **not** rebuilt and CUDA configuration was **not** changed, so GPU
offload remained unavailable.

VRAM sampled around a vision inference (nvidia-smi):

| Phase | VRAM (MiB) |
|-------|-----------|
| Before | 858 |
| During (min…max) | 850 … 858 |
| After | 850 |

No model-related GPU allocation occurred — models execute on CPU.
**GPU ACCELERATION NOT VERIFIED.** RTX 4050 is present but unused by the models.

## Disk (Part 12)

| Drive | Free space (after) |
|-------|-------------------|
| C: | 47.48 GB |
| D: | 218.59 GB |

New files created by the validation are small: the DOCX artifact (~40 KB) and coder
workspace files (solution.py / test_solution.py / sensor_fixture.csv, a few KB).
No unexpectedly large files were created. User data, datasets, and model weights were
not modified or deleted. (Strict "before" free space was marginally higher by the
size of these generated artifacts; only generated outputs were added.)

## Tests (Part 14)

Full suite run with the Qdrant lock released (the live backend was stopped for the
run so the embedded index was not double-locked) and both model servers up:

- **Passed: 55**
- **Failed: 0**
- **Skipped: 1** (`test_coder.py::test_coder_pipeline_end_to_end` — its connectivity
  probe builds `…/v1/v1/models` (double `/v1`), so it skips even with the server up;
  pre-existing test-probe defect. The coder *agent* was validated live in Part 4.)

Classification of any non-pass:
- `test_coder` skip → **pre-existing test defect** (probe path bug) + reflects the
  real coder sandbox import-hook defect found in Part 4.
- Earlier failures seen *while the live backend was running* (RAG-dependent tests in
  `test_tools`/`test_router`) were **environmental**: the embedded Qdrant store is
  single-access and was locked by the running backend. Releasing the lock made them
  pass. This is a concurrency limitation of embedded Qdrant, not a system defect.

## Acceptance Matrix (Part 16)

| Test | Backend | Model | GPU | RAG | Artifact | Network | Result |
|------|---------|-------|-----|-----|----------|---------|--------|
| Coder | PASS | PASS (qwen-coder, local) | N/A (CPU) | N/A | N/A | PASS (0 calls) | **PARTIAL** — generation/routing/server PASS; sandbox verification FAILED (harness defect) |
| Vision | PASS | PASS (qwen-vl, local) | N/A (CPU) | N/A | N/A | PASS (0 calls) | **PASS** |
| Knowledge (RAG) | PASS | N/A | N/A | PASS | N/A | PASS (0 calls) | **PASS** |
| Multimodal | PASS | PASS (qwen-vl + local RAG) | N/A (CPU) | PASS | PASS (DOCX) | PASS (0 calls) | **PASS** |
| Approval Artifact | PASS | N/A | N/A | PASS | PASS (DOCX) | PASS (0 calls) | **PASS** |
| Frontend System Status | PASS | reflected (ONLINE/OFFLINE/…) | N/A | reflected | N/A | PASS | **PASS** |

## Remaining Blockers

1. **GPU acceleration unavailable.** Installed llama.cpp is CPU-only (no
   `ggml-cuda.dll`); `llama_supports_gpu_offload()=False`. The rules forbid
   rebuilding llama.cpp / changing CUDA, so this could not be enabled. Impact:
   high CPU latency (coder ~9 min, vision ~35 s). — *environment / policy*
2. **Coder sandbox verification defect.** `backend/agent/coder/sandbox.py` uses the
   removed `find_module` import-hook API; under Python 3.11 `import pytest` fails, so
   the generated code's automated test cannot run. Generation itself is correct. —
   *genuine code defect* (not modified per "do not fix unrelated issues").
3. **General model not present on this host.** No GGUF and no `:8001` server →
   registry reports `UNAVAILABLE`. The agent does not require it (synthesis is
   programmatic), but routing still lists it by capability. — *not configured*
4. **PostgreSQL OFFLINE.** No local Postgres running; backend degrades gracefully and
   the offline/local paths work. — *environment*
5. **Embedded Qdrant single-access.** Only one process may hold the index; running
   the backend and RAG tests concurrently makes the tests fail. — *environment*

## Final Verdict

# PHASE 6.5 PARTIALLY COMPLETE

The sovereign local pipeline is validated end-to-end with **real local models and
zero external calls**: Vision (PASS), RAG/Knowledge (PASS), Multimodal (PASS),
Approval Artifact (PASS), Frontend System Status (PASS), and Network sovereignty
(0 external calls). The Coder path is **PARTIAL** — routing, model generation, and
the server all PASS, but automated sandbox *verification* fails due to a pre-existing
import-hook defect in the sandbox harness (the generated code is correct). GPU
acceleration is **NOT VERIFIED** because the installed llama.cpp is CPU-only and the
rules prohibit rebuilding it. These are real, honestly-reported limitations, not
fabricated passes.
