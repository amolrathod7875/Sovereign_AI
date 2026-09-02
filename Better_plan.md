# Better_plan.md — Sovereign AI

> **This document is the canonical architecture spec for Sovereign AI.**
> Open it when you need to know *what the system is*, *what has been
> built*, *what has been validated*, and *what is still open*.
>
> Last revised: Phase 11.9 — production configuration & reproducibility (2026-09-02).

---

## Table of contents

1. [What Sovereign AI is today](#1-what-sovereign-ai-is-today)
2. [Current architecture](#2-current-architecture)
3. [Current model + runtime state](#3-current-model--runtime-state)
4. [Current security boundary](#4-current-security-boundary)
5. [Current test status](#5-current-test-status)
6. [Status table by area](#6-status-table-by-area)
7. [Recent completed phases](#7-recent-completed-phases)
8. [Known limitations](#8-known-limitations)
9. [Immediate next phases](#9-immediate-next-phases)
10. [Longer-term roadmap](#10-longer-term-roadmap)
11. [Original PS 26117 requirements → current coverage](#11-original-ps-26117-requirements--current-coverage)

---

## 1. What Sovereign AI is today

Sovereign AI is a self-hosted, air-gapped AI workbench for
confidential industrial work. It is a **FastAPI + LangGraph**
backend, a **React + Vite** frontend, and a curated set of
**open-weight GGUF models** running locally through
**llama-cpp-python**.

It is a **sovereign runtime**: every model, embedder, vector store,
reranker, and code-execution sandbox runs on the host machine. There
is no cloud AI API, no cloud vector DB, no cloud OCR, no cloud file
storage, no cloud embeddings, no cloud reranker. The
`NetworkGuard` enforces this in code; the **Network Monitor** UI
proves it live.

**Today, on a single host (RTX 4050 / Ryzen 5 5600G, Windows 11, Python 3.11):**

- The backend runs at `http://localhost:8000`.
- The frontend runs at `http://localhost:3000` and proxies to `:8000`.
- The **coder model** (Qwen2.5-Coder-3B-Instruct Q4_K_M) is live
  on `:8002` — **CUDA-accelerated on RTX 4050**, validated at
  **~32.7 tokens/sec** with all 36 layers on GPU.
- The **vision model** (Qwen2.5-VL-3B-Instruct Q4_K_M + mmproj Q8_0)
  is live on `:8003` — **CUDA-accelerated on RTX 4050**, validated at
  **~23.3 tokens/sec** with all layers on GPU.
- The **general model** is reserved in the router and registry at
  `:8001`, but the GGUF weights have not been provisioned; routing
  through the general path currently returns
  `used: false, reason: "general model server not running on this host"`.
- The RAG index is 393 chunks over the embedded Qdrant store
  (`sovereign_knowledge`, 384-dim cosine) and a bm25s index.
- The four golden demos (inspection-approval, data-analysis,
  multimodal, correspondence-search) are documented in `reports/`
  and have been exercised end-to-end in past phases against the
  CPU serving layer.

---

## 2. Current architecture

```
USER
  │
  ▼
+--------------------------------------------------------------+
|  REACT + VITE FRONTEND  (frontend/)                          |
|  Workbench · Network Monitor · VisionResult (honest) · …     |
+----------------------------+---------------------------------+
                             │  /api/*  (Axios, two timeouts)
                             ▼
+--------------------------------------------------------------+
|  FASTAPI BACKEND  (backend/app)                              |
|  /chat /agent /coder /vision /documents /rag /models         |
|  /sandbox /executions /artifacts /system /network            |
+----------+-----------------+--------------------+-----------+
           │                 │                    │
           ▼                 ▼                    ▼
+-----------------+  +-----------------+  +-------------------+
| LANGGRAPH AGENT |  |   RAG PIPELINE  |  |  SECURITY LAYER   |
| (backend/agent) |  | Qdrant + BM25   |  |  NetworkGuard     |
|  planner→route  |  |  (backend/rag)  |  |  NetworkMonitor   |
|  →retrieve→tool |  |  393 chunks     |  |  Coder sandbox    |
|  →verify→deliver|  |                 |  |  Piston boundary  |
+--------+--------+  +--------+--------+  +---------+---------+
         │                    │                     │
         ▼                    ▼                     ▼
+-------------------+ +-------------------+ +-------------------+
| LOCAL MODEL LAYER | |  EMBEDDED QDRANT  | |  INGRESS / DB     |
|  llama-cpp-python | |  on-disk          | |  PostgreSQL       |
|  + FastAPI        | |  + bm25s index    | |  Local FS         |
|  (serve_model.py) | |                   | |  Piston (sandbox) |
+--------+----------+ +-------------------+ +-------------------+
         │
         ├─ :8001 general  (reserved, weights absent)
         ├─ :8002 coder    (Qwen2.5-Coder-3B-Instruct Q4_K_M, CUDA validated)
         └─ :8003 vision   (Qwen2.5-VL-3B + mmproj, CPU validated)
```

### Backend trees

| Tree              | Purpose                                                          |
|-------------------|------------------------------------------------------------------|
| `backend/app/`    | Production FastAPI app (routes, RAG, models, security, storage)  |
| `backend/agent/`  | Standalone LangGraph agent (`graph.py`, `nodes/`, `coder/`, `tools/`, `security/`) |
| `backend/rag/`    | Standalone RAG package (Qdrant + bm25s + hybrid retrieval)       |
| `backend/ingestion/` | Phase 1 + 1.5 ingestion subsystem (separate FastAPI + CLI)    |
| `backend/tests/`  | pytest suite (~120 tests across 11 files)                        |
| `backend/scripts/`| Internal E2E helpers (e.g. `run_coder_e2e.py`)                   |

### Frontend pages

`Workbench`, `Dashboard`, `KnowledgeBase`, `ExecutionTrace`,
`ModelRegistry`, `Artifacts`, `NetworkMonitor`, `System`. All are
hand-written React 18 + Vite 5 + Tailwind 3. The API client lives in
`frontend/src/lib/api/client.ts` (two axios instances — 30 s control
timeout, 2 400 s inference timeout). Vision honesty lives in
`frontend/src/lib/utils.ts:isVisionUnavailable()` and the
`VisionResult` component, which renders a
`VISION ANALYSIS UNAVAILABLE` panel when the VLM is not reachable.

---

## 3. Current model + runtime state

### 3.1 Model table (what is actually loaded on a fresh host)

| ID            | Weights                                                                                              | Endpoint            | Runtime                                                | Status                       |
|---------------|------------------------------------------------------------------------------------------------------|---------------------|--------------------------------------------------------|------------------------------|
| `general`     | **absent**                                                                                           | `:8001/v1`          | (server not running)                                   | standby (no server)          |
| `qwen-coder`  | `models/qwen-coder/qwen2.5-coder-3b-instruct-q4_k_m.gguf` (1.96 GB)                                  | `:8002/v1`          | llama-cpp-python 0.3.35 + CUDA 12.4 + AVX2, sm_89      | **online, CUDA validated**   |
| `vision`      | `models/qwen-vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` (1.80 GB) + `mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf` (0.79 GB) | `:8003/v1` (`qwen2-vl` chat-format) | llama-cpp-python 0.3.35 + CUDA 12.4 + AVX2, sm_89      | **online, CUDA validated**   |
| `embedding`   | `sentence-transformers/all-MiniLM-L6-v2` (offline, 384-dim)                                          | local               | local                                                  | online                       |
| `reranker`    | local BGE-style reranker                                                                             | local               | local                                                  | online                       |

### 3.2 Coder CUDA build (Phase 11.4)

- **Build:** `pip install .` from `llama_cpp_python-0.3.35` source
  with `CMAKE_ARGS="-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89
  -DGGML_AVX=ON -DGGML_AVX2=ON -DGGML_AVX512=OFF
  -DGGML_NATIVE=OFF"`, `CMAKE_GENERATOR=Ninja`,
  `--no-build-isolation --force-reinstall`.
- **Toolchain:** MSVC 19.44 (cl 19.44.35228), nvcc 12.4.99,
  cmake 4.4.3 (pip), ninja 1.13.2 (pip), CUDA 12.4.99, Windows
  SDK 10.0.26100.
- **Why Ninja, not Visual Studio generator:** the CUDA 12.4 install
  has no `Nvcc.targets` MSBuild integration, so the VS generator
  fails with "No CUDA toolset found". Ninja invokes `nvcc` directly
  and bypasses the problem.
- **Why `sm_89`:** RTX 4050 reports compute capability 8.9.
- **Why AVX-512 OFF:** the AMD Ryzen 5 5600G has no AVX-512; the
  0.3.35 default `GGML_AVX512=ON` build would crash the model init
  with `OSError: [WinError -1073741795]`. Verified AVX2-only works
  end-to-end.
- **Resulting DLLs** in
  `Lib\site-packages\llama_cpp\lib\`:
  `ggml-cuda.dll` (180 MB), `ggml-base.dll`, `ggml-cpu.dll`,
  `ggml.dll`, `llama.dll`, `mtmd.dll`. `ggml-cuda.dll` depends on
  `cudart64_12.dll`, `cublas64_12.dll`, `nvcuda.dll` (resolved from
  `CUDA_PATH\bin`, auto-added by `llama_cpp/_ctypes_extensions.py`).
- **Measured:** `n_gpu_layers=99, n_ctx=2048` → VRAM
  **840 MiB → 3 132 MiB** (delta ≈ 2.3 GB),
  **~32.7 tokens/sec** for short completions. The build is
  reproducible; the prebuilt CPU wheel
  (`_rollback/llama_cpp_python-0.3.35-cpu-py3-none-win_amd64.whl`,
  SHA-256 verified) is the rollback.

### 3.3 Runtime ports

| Port | Service                                  | Binding               |
|------|------------------------------------------|-----------------------|
| 8000 | Backend (FastAPI)                        | `0.0.0.0`             |
| 8001 | General LLM                              | loopback (reserved)   |
| 8002 | Coder LLM                                | loopback              |
| 8003 | Vision LLM                               | loopback              |
| 3000 | Frontend (Vite dev)                      | loopback              |
| 6333 / 6334 | Qdrant (HTTP / gRPC)               | container             |
| 5432 | PostgreSQL                               | container             |
| 2000 | Piston (sandbox)                         | container             |

### 3.4 RAG

- **Chunks:** 393 (verified: `data/rag/qdrant_db/collection/sovereign_knowledge/storage.sqlite` points = 393; matching BM25 corpus entries).
- **Collection:** `sovereign_knowledge`, 384-dim, cosine, on-disk at
  `data/rag/qdrant_db/`.
- **Sparse index:** `data/rag/bm25/bm25_index/`, corpus at
  `data/rag/bm25/corpus.json`.
- **Fusion:** weighted sum, `0.7 × dense + 0.3 × bm25`
  (`backend/rag/retrieval/hybrid.py:42-58`).
- **Embedder:** `sentence-transformers/all-MiniLM-L6-v2`, offline
  (`HF_HUB_OFFLINE=1`).
- **A second Qdrant client** (`backend/app/storage/qdrant.py`)
  serves `/api/rag/*`; the agent path uses the embedded on-disk
  store authoritatively.

### 3.5 Code sandbox

`backend/agent/coder/sandbox.py` runs each coder request in a child
Python interpreter with:
- PEP 451 import hook blocking `socket`, `urllib`, `requests`, `http`,
  `subprocess`, `smtplib`, `ftplib`, `telnetlib`, `paramiko`,
  `webbrowser`, `poplib`, `imaplib`, `nntplib`, `http.client`, `ssl`.
- `subprocess` stub raising `PermissionError` on all
  process-creation APIs.
- `os.system` / `os.exec*` / `os.spawn*` stubbed to raise.
- `builtins.open` scoped to a workspace directory.
- `socket.socket.connect` strict allow-list (loopback only — even
  RFC1918 is rejected inside the child).
- Wall-clock timeout via `subprocess.run(timeout=…)`.
- `external_network_calls: 0` is asserted on every result.

`/api/sandbox/execute` additionally wraps the **Piston** endpoint
(`http://piston:2000`) for arbitrary code execution; the boundary
is enforced by `validate_local_endpoint`.

---

## 4. Current security boundary

Sovereign AI is a sovereign runtime. The boundary is enforced by
**NetworkGuard** (`backend/agent/security/netguard.py`) and made
visible by the **NetworkMonitor** UI.

### 4.1 Trusted-local allow-list (positive)

| Range              | Purpose                              |
|--------------------|---------------------------------------|
| `127.0.0.0/8`      | IPv4 loopback                         |
| `::1/128`          | IPv6 loopback                         |
| `10.0.0.0/8`       | RFC1918 private                       |
| `172.16.0.0/12`    | RFC1918 private                       |
| `192.168.0.0/16`   | RFC1918 private                       |

Hostname allow-list: `{localhost, 127.0.0.1, ::1}`.

### 4.2 Explicitly not trusted (and verified blocked)

| Range              | Reason                                              |
|--------------------|------------------------------------------------------|
| `169.254.0.0/16`   | IPv4 link-local — includes cloud metadata `169.254.169.254` |
| `fe80::/10`        | IPv6 link-local                                      |
| `192.0.2.0/24`     | RFC5737 TEST-NET-1 (documentation)                   |
| `198.51.100.0/24`  | RFC5737 TEST-NET-2 (documentation)                   |
| `203.0.113.0/24`   | RFC5737 TEST-NET-3 (documentation)                   |
| `198.18.0.0/15`    | RFC2544 benchmarking                                 |
| `fc00::/7`         | IPv6 unique local addresses (ULA)                    |
| `100.64.0.0/10`    | CGNAT                                                |
| `0.0.0.0`, `255.255.255.255` | unspecified / broadcast                       |
| `224.0.0.0/4`      | multicast                                            |
| Any hostname requiring DNS resolution | unresolvable → rejected as not-local |

Coverage: 28 parametrized tests in `backend/tests/test_netguard.py`,
including the dedicated cloud-metadata and hostname-lookalike cases.
The trust list is **positive**: anything not matching falls through
to the block branch (`netguard.py:73-88`).

The **coder child sandbox** is stricter: only `ip.is_loopback` is
permitted for outbound sockets — the sandbox is supposed to be
self-contained and has no reason to talk to RFC1918 hosts.

### 4.3 Parallel monitors

- `backend/app/security/network_monitor.py` is a separate,
  pattern-detecting class that flags hard-coded cloud AI domains
  (`api.openai.com`, `api.anthropic.com`, `api.cohere.ai`,
  `api.huggingface.co`, `generativeai.googleapis.com`,
  `aiplatform.googleapis.com`). It does not enforce — it surfaces.
- `GET /api/network/monitor` (SSE) and `GET /api/network/events`
  (history) stream these events to the Network Monitor page.

---

## 5. Current test status

| Suite                                             | Approx. tests | Status |
|---------------------------------------------------|---------------|--------|
| `backend/tests/test_netguard.py`                  | 28            | PASS (parametrized over every CIDR family in §4) |
| `backend/tests/test_router.py`                    | 16            | PASS  |
| `backend/tests/test_coder_sandbox.py`             | 29            | PASS  |
| `backend/tests/test_vision.py`                    | 10            | PASS  |
| `backend/tests/test_piston_security.py`           | 10            | PASS  |
| `backend/tests/test_agent.py` + `test_agent_e2e.py` | 9            | PASS  |
| `backend/tests/test_phase10_4.py`                 | 12            | PASS (Phase 10.4 inference reliability) |
| `backend/tests/test_coder.py` + `test_tools.py`   | 7             | PASS  |
| `backend/rag/tests/test_retrieval.py`             | (Phase 3 retrieval) | PASS |
| `backend/ingestion/tests/`                        | 3 files       | PASS  |
| `frontend/` (Vitest)                              | 3 files       | PASS  |

`pytest tests/ -v` is the canonical backend command; the suites
are wired so a regression in any layer fails the run.

---

## 6. Status table by area

| Area                         | Current state                                                       | Status        |
|------------------------------|----------------------------------------------------------------------|---------------|
| FastAPI backend              | Production app at `:8000`, all 12+ API surfaces live                | **COMPLETE**  |
| LangGraph agent              | `backend/agent/` — planner, route, retrieve, generate, verify, vision | **COMPLETE** |
| Local model serving          | `scripts/serve_model.py` (llama-cpp-python + FastAPI, OpenAI-compat) | **COMPLETE** |
| Coder — Qwen2.5-Coder-3B CPU | live on `:8002`                                                     | **COMPLETE**  |
| Coder — Qwen2.5-Coder-3B CUDA| **RTX 4050 validated, ~32.7 t/s, sm_89, AVX2**                       | **COMPLETE**  |
| Vision — Qwen2.5-VL CPU      | live on `:8003`, honest disclosure on failure                       | **COMPLETE**  |
| Vision — Qwen2.5-VL CUDA     | **RTX 4050 validated, ~23.3 t/s, sm_89, AVX2**                      | **COMPLETE**  |
| General LLM weights          | router + endpoint reserved, GGUF absent                              | **BLOCKED** (provisioning) |
| RAG — Qdrant + BM25          | 393 chunks, weighted hybrid, citations                               | **COMPLETE**  |
| Embeddings (offline)         | `all-MiniLM-L6-v2` 384-dim                                            | **COMPLETE**  |
| NetworkGuard                 | explicit trusted-local CIDRs, 28 tests                               | **COMPLETE**  |
| Coder sandbox                | PEP 451 import hook + socket guard + timeout                        | **COMPLETE**  |
| Piston boundary              | validated                                                            | **COMPLETE**  |
| Network Monitor UI           | SSE + history, displayed counter                                     | **COMPLETE**  |
| Honest vision disclosure     | `isVisionUnavailable()` + frontend banner (Phase 8.1)                | **COMPLETE**  |
| DOCX artifacts               | `python-docx` tool, used in approval-note demo                       | **COMPLETE**  |
| XLSX artifacts               | `openpyxl`, used in data-analysis demo                               | **COMPLETE**  |
| PPTX artifacts               | `python-pptx` pinned, no consumer wired in `backend/app`             | **IN PROGRESS** (library present, no API surface) |
| E2E harness                  | per-phase suites + agent E2E                                         | **COMPLETE**  |
| Phase 9 / 10 / 11 reports    | committed to git as commit messages; not yet in `reports/`           | **DEFERRED** (re-issue as `reports/phase{9,10,11}_*.md`) |
| GPU concurrency              | one model at a time on the 6 GB RTX 4050 (sequential loading)        | **DEFERRED**  |
| PaddleOCR in-app             | separate environment (protobuf conflict with `qdrant-client`)        | **DEFERRED**  |
| Lovable frontend             | original spec; actual is hand-written React+Vite                      | **OBSOLETE**  |
| vLLM as model serving        | compose profile still exists; actual is llama-cpp-python            | **OBSOLETE**  |
| AWQ quantization             | compose still references; actual is GGUF                             | **OBSOLETE**  |

---

## 7. Recent completed phases

These are the milestones that produced code, tests, or both — and
that are now reflected in this document. Where a `reports/phaseX_Y_*.md`
write-up exists, it is cited; otherwise the work is described here.

| Phase     | Title                                          | Evidence                                                                                                       | Report                                       |
|-----------|------------------------------------------------|----------------------------------------------------------------------------------------------------------------|----------------------------------------------|
| 8.1       | Multimodal disclosure / honest vision availability | `frontend/src/lib/utils.ts:isVisionUnavailable`, `Workbench.tsx:VisionResult`                              | `reports/phase8_1_multimodal_disclosure.md`  |
| 8.2       | Post-merge regression fixes                    | `git log` shows `d5913a5 Phase 8.2 post-merge regression fixes`                                                | `reports/phase8_2_post_merge_regression.md`  |
| 9.1       | Controlled backend startup and health validation | `backend/app/main.py` lifespan + `init_db` + `init_qdrant`; `backend/app/api/system.py` health endpoint      | (roll-up)                                    |
| 9.2       | Local llama.cpp model server preflight         | `scripts/serve_model.py` smoke-tested; `local` flag on every registry entry                                    | (roll-up)                                    |
| 9.3       | Local coder server validation                  | `qwen-coder` registry entry + `serve_model.py --model-id qwen-coder`; tested through `backend/scripts/run_coder_e2e.py` | (roll-up)                              |
| 9.4       | Local Qwen2.5-VL vision server validation      | `vision` registry entry + `serve_model.py --model-id qwen-vision --mmproj … --chat-format qwen2-vl`           | (roll-up)                                    |
| 9.5       | Full-stack local smoke test                    | `backend/tests/test_agent_e2e.py` exercises the full graph; `backend/tests/test_vision.py` exercises vision  | (roll-up)                                    |
| 9.6       | E2E harness repair and real integration        | `cb325c5 Phase 9.6 fix E2E backend configuration`                                                                | (roll-up)                                    |
| 10.1      | Explicit vision + RAG E2E coverage             | `3a7b0c0 Phase 10.1 add vision and RAG E2E coverage`; `test_phase10_4.py` for downstream regressions         | (roll-up)                                    |
| 10.2      | Network / security validation + secondary fixes| (roll-up)                                                                                                       | (roll-up)                                    |
| 10.3      | NetworkGuard boundary correction               | `85b1036 Phase 10.3 harden network sovereignty boundary`                                                        | (roll-up)                                    |
| 10.4      | Coder task propagation + timeout + vision timeout | `dcd20d7 Phase 10.4 harden inference reliability`; `backend/tests/test_phase10_4.py` (12 tests)            | (roll-up)                                    |
| 11.1      | CUDA / llama.cpp GPU preflight                 | toolchain verified (cl, nvcc, cmake, ninja); CUDA 12.4 path identified                                          | (roll-up)                                    |
| 11.2      | Official CUDA wheel blocked by AVX-512         | prebuilt CUDA wheel `OSError: [WinError -1073741795]` on Ryzen 5 5600G (no AVX-512)                            | (roll-up)                                    |
| 11.3      | CUDA source-build preflight                    | full toolchain re-verified in vcvarsall; flags sourced from `vendor/llama.cpp/ggml/CMakeLists.txt`            | (roll-up)                                    |
| 11.4      | CUDA + AVX2 llama.cpp source build validated   | `pip install .` succeeded; `ggml-cuda.dll` 180 MB installed; full model offload to GPU observed              | this document §3.2; `_rollback/build7.log`   |
| 11.6      | Vision CUDA validation                         | Qwen2.5-VL-3B-Instruct CUDA validated on RTX 4050; best ngl=99, ~10.06 t/s, peak 5 825 MiB                  | (roll-up)                                    |
| 11.7      | GPU memory, performance & concurrency          | Best coder ngl=40 (42.18 t/s, 3 177 MiB init); concurrent peak 5 699–5 771 MiB                             | (roll-up)                                    |
| 11.8      | CPU vs CUDA performance benchmark              | Coder 3.08x latency / 3.11x TPS; vision 3.31x latency / 3.47x TPS; RAG ~35.6 ms                           | (roll-up)                                    |

> Phase 9/10/11 per-phase write-ups were captured in commit
> messages rather than as `reports/phase{9,10,11}_*.md` files. If
> you need the detailed timeline, read the git history
> (`git log --oneline`).

---

## 8. Known limitations

- **General LLM weights are not provisioned.** The endpoint
  (`:8001/v1`), the registry entry, the router path, and the
  `/api/system/status` reporting are all in place. Provisioning a
  small Qwen 2.5 3B Instruct GGUF into `models/qwen-general/` would
  make the path live with **no code change**.
- **Vision CUDA is VRAM-constrained.** Validated for the tested workload
  (Qwen2.5-VL-3B-Instruct Q4_K_M, peak ~5 832 MiB on RTX 4050). Monitor
  VRAM under production workloads; arbitrary high-resolution workloads
  have not been tested.
- **GPU concurrency is conditional.** Concurrent multi-model GPU
  inference was tested with peak VRAM 5 699–5 771 MiB (under the
  5 800 MiB safety limit). Production concurrency should be monitored
  and is not guaranteed under arbitrary workloads.
- **PaddleOCR is in a separate environment.** The Qdrant client
  pins `protobuf<6`, which conflicts with `paddlepaddle>=2.5`.
  PaddleOCR is installed and exercised in its own environment
  per `prerequistes/PaddleOCR.md`; it is not imported in the
  `backend/app` path. The multimodal pipeline is exercised via
  the local VLM.
- **Single-host only.** The compose stack assumes one host per
  deployment; the router does not fan out across nodes.
- **Windows Long Path support is not enabled.** Re-running the
  CUDA source build on this host required extracting the source
  to a short path (`C:\src\llama_cpp\`) because the vendored UI
  contains deeply-nested `.svelte` paths that exceed `MAX_PATH`.
- **No Phase 9 / 10 / 11 reports under `reports/`.** Those
  phases' details live in commit messages and this document.

---

## 9. Immediate next phases

1. **Phase 11.5 — Documentation sync** (this phase). ✅
2. **Phase 11.9 — Production configuration & reproducibility** (this phase). ✅
3. **Phase 13 — General LLM provisioning.** Download a small
   Qwen 2.5 3B Instruct GGUF into `models/qwen-general/`; start
   the server; add a smoke test that asserts the router reaches
   the endpoint.
4. **Phase 14 — Per-phase `reports/` write-ups.** Re-issue the
   Phase 9/10/11 roll-ups as standalone `reports/phase{9,10,11}_*.md`
   files so the audit trail is browsable without `git log`.

---

## 10. Longer-term roadmap

- **PPTX artifacts in the API surface.** The library is pinned;
  no `app/api/pptx.py` exists yet. Wire it as a coder-tool
  output alongside DOCX.
- **Reranker tuning.** The weighted fusion `0.7/0.3` is a
  baseline. Add a sweep over the Qwen 2.5-Coder "relevance"
  judgements from the synthetic dataset.
- **Windows Long Path support.** Enable the Windows Long Path
  group policy so future CUDA rebuilds can run from the standard
  `pip` install path.
- **Re-run the 4 golden demos against the CUDA coder.** Update
  each demo's `reports/` write-up with the post-CUDA tps numbers.
- **GPU concurrency experiment.** Once a second 6 GB GPU is
  available, exercise two concurrent GGUF servers; record the
  achievable throughput per model.

---

## 11. Original PS 26117 requirements → current coverage

| PS 26117 requirement                                  | Covered in current implementation                                                |
|-------------------------------------------------------|-----------------------------------------------------------------------------------|
| Self-hosted, air-gapped                               | §4 (NetworkGuard + Network Monitor UI), `infra/.env.example` (no external URLs)  |
| Not locked to one model                               | `backend/app/models/registry.py` (5 entries, `local=True`)                        |
| Multiple open-weight models                            | Qwen2.5-Coder-3B + Qwen2.5-VL-3B + (planned) Qwen2.5-3B-Instruct                  |
| Auto-select right model per task                      | `backend/app/models/router.py` (capability-based dispatch)                        |
| Add models without redesign                           | `register_model()` in registry; no router changes required                        |
| Agentic (plan, iterate, multi-step)                   | `backend/agent/graph.py` + `nodes/` (analyze/calculate/decide/plan/retrieve/synthesize/verify) |
| Local tools (file, code sandbox, spreadsheet, search) | `backend/agent/tools/`, `backend/agent/coder/sandbox.py`, `python-docx`/`openpyxl`|
| Scanned PDFs, handwritten notes, drawings             | `backend/agent/tools/vision.py` (VLM), PyMuPDF, PaddleOCR (separate env)         |
| Real deliverables (Word / Excel / PPT / code)         | DOCX ✅, XLSX ✅, PPTX **library pinned, not wired**, `.py` coder artifact ✅      |
| Local knowledge base (SOPs, manuals, correspondence)  | `backend/rag/` over 393 chunks from `data/synthetic/` + `demo-data/`             |
| Visible network monitor                               | `frontend/src/pages/NetworkMonitor.tsx` + `/api/network/monitor` SSE              |
| Four golden demos (equal priority)                    | Re-runnable via `backend/scripts/` and per-phase suites; coverage proven in Phases 5–8 + 9.5/9.6 |

---

## Appendix A — File-and-line index of the most-cited references

| Topic                            | File:line                                              |
|----------------------------------|--------------------------------------------------------|
| FastAPI app entry                | `backend/app/main.py:38`                                |
| NetworkGuard definition          | `backend/agent/security/netguard.py:91-148`             |
| NetworkGuard trust list          | `backend/agent/security/netguard.py:27-33`              |
| NetworkGuard block branch        | `backend/agent/security/netguard.py:73-88`              |
| Registry trusted-local mirror    | `backend/app/models/registry.py:42-48`                  |
| Registry endpoints               | `backend/app/models/registry.py:90-92`                  |
| Router (primary)                 | `backend/app/models/router.py:189-286`                  |
| Router execute (no_network wrap) | `backend/app/models/router.py:303-376`                  |
| Qdrant embedded client           | `backend/rag/indexing/qdrant_store.py:11, 24`           |
| Qdrant server-style client       | `backend/app/storage/qdrant.py:11, 19`                  |
| BM25 store                       | `backend/rag/indexing/bm25_store.py:12, 35`             |
| Hybrid retrieval (weighted sum)  | `backend/rag/retrieval/hybrid.py:42-58`                 |
| Coder sandbox                    | `backend/agent/coder/sandbox.py:86-301`                 |
| Vision tool                      | `backend/agent/tools/vision.py` (657 lines)             |
| Vision endpoint config           | `backend/agent/config.py:36-37`                         |
| Vision API route                 | `backend/app/api/vision.py:54-101`                      |
| Vision unavailable disclosure    | `frontend/src/lib/utils.ts:78-100`                      |
| Workbench component              | `frontend/src/pages/Workbench.tsx:73-389`               |
| Network Monitor component        | `frontend/src/pages/NetworkMonitor.tsx` (210 lines)     |
| Network Monitor SSE endpoint     | `backend/app/api/network.py:14-26`                      |
| Frontend API client              | `frontend/src/lib/api/client.ts` (293 lines)            |
| Local model launcher             | `scripts/serve_model.py:24-107`                         |
| Backend config / ports           | `backend/app/config.py:11-63`                           |
| CORS allow-list                  | `backend/app/config.py:55-59` + `backend/app/main.py:50-57` |
| Backend requirements             | `backend/requirements.txt`                              |
| Frontend package                 | `frontend/package.json`                                 |
| docker-compose GPU               | `infra/docker-compose.yml:68-132`                       |
| docker-compose CPU               | `infra/docker-compose.cpu.yml:1-77`                     |
| env example                      | `infra/.env.example`                                    |
| RAG chunks (verified 393)        | `data/rag/qdrant_db/collection/sovereign_knowledge/storage.sqlite` |
| CPU fallback wheel               | `_rollback/llama_cpp_python-0.3.35-cpu-py3-none-win_amd64.whl` |
| Source tarball                   | `_rollback/llama_cpp_python-0.3.35-source.tar.gz`       |
