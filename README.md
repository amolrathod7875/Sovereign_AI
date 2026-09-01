# Sovereign AI

Self-hosted, air-gapped AI workbench for confidential industrial work.

Sovereign AI is a fully local FastAPI + LangGraph backend, a React + Vite
frontend, and a curated set of open-weight GGUF models. Every model,
embedder, vector store, reranker, and code-execution sandbox runs on the
host machine. No external AI service is ever contacted. A network
guard and a real-time network monitor prove this in the UI.

---

## Table of contents

- [Architecture](#architecture)
- [Local inference](#local-inference)
- [Models](#models)
- [RAG](#rag)
- [Security model](#security-model)
- [Ports](#ports)
- [Quick start](#quick-start)
- [Project layout](#project-layout)
- [Testing](#testing)
- [Known limitations](#known-limitations)
- [Roadmap](#roadmap)

---

## Architecture

| Layer            | Technology                                                            |
|------------------|-----------------------------------------------------------------------|
| Frontend         | React 18 + TypeScript + Vite 5 + Tailwind CSS                        |
| Backend API      | Python 3.11 + FastAPI 0.115 + Pydantic 2 + uvicorn                   |
| Agent runtime    | LangGraph 0.2 + LangChain 0.3                                        |
| Model serving    | **llama-cpp-python 0.3.35** (OpenAI-compatible FastAPI wrapper)      |
| Vector DB        | Qdrant (embedded on-disk) + BM25 (bm25s)                             |
| Embeddings       | sentence-transformers (`all-MiniLM-L6-v2`, 384-dim, offline)         |
| Reranker         | Local BGE-style reranker                                              |
| Document parser  | PyMuPDF (digital PDF text + page metadata)                           |
| OCR              | PaddleOCR (separate environment, see `prerequistes/PaddleOCR.md`)    |
| Code sandbox     | In-process `agent/coder/sandbox.py` (PEP 451 import hook + socket guard) — Piston adapter available for `/api/sandbox/execute` |
| Office artifacts | python-docx + openpyxl + python-pptx                                  |
| Relational DB    | PostgreSQL 16                                                         |
| Container runtime| Docker Compose                                                        |

> **Note:** the model serving layer is **llama-cpp-python in every profile**.
> The `docker-compose.yml` ships a `gpu` profile that launches the three
> llama.cpp server containers; the `cpu` profile omits them. On bare
> metal (Windows / Linux), `scripts/serve_model.py` runs one process per
> model on the same dedicated ports.

---

## Local inference

All inference is performed locally. There is no fallback to a remote
provider — if a local server is unreachable, the API returns
`503 Service Unavailable` and the frontend displays an honest
"unavailable" panel (see Phase 8.1).

### Coder — verified on RTX 4050

| Item                  | Value                                                   |
|-----------------------|---------------------------------------------------------|
| Model                 | Qwen2.5-Coder-3B-Instruct, Q4_K_M GGUF (~2.0 GB)        |
| Endpoint              | `http://localhost:8002/v1`                              |
| Server                | `python scripts/serve_model.py --model-id qwen-coder --port 8002` |
| Runtime               | **llama-cpp-python 0.3.35** + CUDA 12.4 + AVX2          |
| GPU                   | NVIDIA RTX 4050, compute capability 8.9 (sm_89)         |
| CPU                   | AMD Ryzen 5 5600G — **AVX2 yes, AVX-512 no**            |
| Build                 | `GGML_CUDA=ON`, `GGML_AVX2=ON`, `GGML_AVX512=OFF`, `CMAKE_CUDA_ARCHITECTURES=89` |
| Measured VRAM (init, all 36 layers on GPU) | ~840 MiB → ~3 132 MiB (delta ≈ 2.3 GB) |
| Measured throughput   | **~32.7 tokens/sec** with `n_gpu_layers=99`, n_ctx=2048 |
| Status                | **CUDA-accelerated local coder inference experimentally validated on RTX 4050** |

The CUDA build is documented in `reports/phase11_4_cuda_source_build.md`
and the CPU prebuilt wheel is cached at
`_rollback/llama_cpp_python-0.3.35-cpu-py3-none-win_amd64.whl` as a
known-good fallback.

### Vision — CPU validated, CUDA pending

| Item         | Value                                                              |
|--------------|--------------------------------------------------------------------|
| Model        | Qwen2.5-VL-3B-Instruct, Q4_K_M GGUF (~1.8 GB)                     |
| mmproj       | `mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf` (~0.8 GB)                |
| Endpoint     | `http://localhost:8003/v1` (chat-format `qwen2-vl`)                |
| Server       | `python scripts/serve_model.py --model-id qwen-vision --port 8003` |
| CPU inference| **Validated**                                                      |
| CUDA inference| **Not yet validated** — `n_gpu_layers` flag is wired but the VLM path has not been benchmarked on RTX 4050 |

### General — server present, weights absent

| Item     | Value                                                     |
|----------|-----------------------------------------------------------|
| Endpoint | `http://localhost:8001/v1` (declared in registry)         |
| Weights  | **No GGUF downloaded for this role yet**                  |
| Status   | `execute_routing` returns `{used: false, reason: "general model server not running on this host"}` |

The general model is reserved in the router and registry so task
classification can already be exercised end-to-end. Provisioning a
small Qwen 2.5 3B Instruct GGUF into `models/qwen-general/` would
make this path live without any code change.

---

## Models

| ID            | Display name                  | Endpoint              | Weights                                          | Status                                |
|---------------|-------------------------------|-----------------------|--------------------------------------------------|---------------------------------------|
| `general`     | Qwen2.5-3B-Instruct           | `:8001/v1`            | **absent**                                       | standby (no server)                   |
| `qwen-coder`  | Qwen2.5-Coder-3B-Instruct     | `:8002/v1`            | `models/qwen-coder/qwen2.5-coder-3b-instruct-q4_k_m.gguf` (1.96 GB) | online — **CUDA validated on RTX 4050** |
| `vision`      | Qwen2.5-VL-3B-Instruct        | `:8003/v1`            | `models/qwen-vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` (1.80 GB) + `mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf` (0.79 GB) | online — **CPU validated, CUDA pending** |
| `embedding`   | BGE-large-en-v1.5             | local                 | `sentence-transformers/all-MiniLM-L6-v2` (384-d) | online                                |
| `reranker`    | BGE-reranker-large            | local                 | local reranker                                   | online                                |

All entries are declared `local=True`; the registry rejects endpoints
that resolve outside the trusted-local CIDR allow-list.

---

## RAG

Hybrid retrieval over an embedded on-disk Qdrant collection
(`sovereign_knowledge`, 384-dim cosine) and a bm25s index.

- **393 chunks** indexed (verified `data/rag/qdrant_db/collection/sovereign_knowledge/storage.sqlite` points = 393; matching BM25 corpus entries).
- **Weighted fusion** rather than RRF: `0.7 × dense + 0.3 × bm25`
  (`backend/rag/retrieval/hybrid.py:42-58`).
- Every chunk carries `document_id`, `page`, `section` for citation
  (`backend/rag/citations.py`).
- Index covers the synthetic plant dataset in `data/synthetic/` plus
  the demo corpus in `demo-data/`.

A second Qdrant client (`backend/app/storage/qdrant.py`) is used by
`/api/rag/*` only; the agent path uses the embedded on-disk store
authoritatively.

---

## Security model

The workbench is a sovereign runtime: **all inference, retrieval,
embedding, OCR, file storage, and code execution stay inside the
deployment boundary**. There is no cloud AI API, no cloud vector DB,
no cloud OCR, no cloud file storage, no cloud embeddings, no cloud
reranker.

**NetworkGuard** (`backend/agent/security/netguard.py`) is the
authoritative allow-list. While active, every `socket.connect` is
inspected; any destination outside the trusted-local CIDR list raises
`ConnectionError` and is recorded on the guard.

Trusted local destinations (positive allow-list):

| Range              | Purpose                            |
|--------------------|------------------------------------|
| `127.0.0.0/8`      | IPv4 loopback                      |
| `::1/128`          | IPv6 loopback                      |
| `10.0.0.0/8`       | RFC1918 private                    |
| `172.16.0.0/12`    | RFC1918 private                    |
| `192.168.0.0/16`   | RFC1918 private                    |

**Explicitly not trusted** (and verified blocked by the test suite):

| Range              | Reason                                  |
|--------------------|------------------------------------------|
| `169.254.0.0/16`   | IPv4 link-local — includes cloud metadata `169.254.169.254` |
| `fe80::/10`        | IPv6 link-local                          |
| `192.0.2.0/24`     | RFC5737 TEST-NET-1 (documentation)       |
| `198.51.100.0/24`  | RFC5737 TEST-NET-2 (documentation)       |
| `203.0.113.0/24`   | RFC5737 TEST-NET-3 (documentation)       |
| `198.18.0.0/15`    | RFC2544 benchmarking                     |
| `fc00::/7`         | IPv6 unique local addresses (ULA)        |
| `100.64.0.0/10`    | CGNAT                                    |
| `0.0.0.0`, `255.255.255.255` | unspecified / broadcast        |
| Any hostname requiring DNS | unresolvable → rejected as not-local |

See `backend/tests/test_netguard.py` (28 tests, parametrized) for the
exhaustive block-list coverage and
`backend/app/security/network_monitor.py` for the parallel
event-stream monitor that surfaces blocks to the UI.

The coder agent's child-Python sandbox
(`backend/agent/coder/sandbox.py`) is stricter still: it only allows
`ip.is_loopback` for outbound sockets, blocks `subprocess` /
`os.system` / network imports via a PEP 451 import hook, and runs
each request in a wall-clock-bounded subprocess.

---

## Ports

| Service          | Default port | Bound to           |
|------------------|--------------|--------------------|
| Backend (FastAPI)| `8000`       | `0.0.0.0`          |
| General LLM      | `8001`       | loopback (`8001` is reserved for the not-yet-deployed general model) |
| Coder LLM        | `8002`       | loopback           |
| Vision LLM       | `8003`       | loopback           |
| Frontend (Vite)  | `3000`       | loopback           |
| Qdrant (HTTP/gRPC)| `6333`/`6334` | container         |
| PostgreSQL       | `5432`       | container          |
| Piston (sandbox) | `2000`       | container          |

The model servers are loopback-only; the backend reaches them at
`http://localhost:800{1,2,3}/v1`. In a containerised deploy these map
to the in-network service names defined in `infra/docker-compose*.yml`.

---

## Quick start

### With GPU (CUDA) — recommended on RTX 4050

The CUDA build of llama-cpp-python is installed in the
`sovereign-ai` conda environment (Phase 11.4). Start the model
servers on bare metal, then the backend:

```bash
# Terminal 1: coder (CUDA, all layers on GPU)
python scripts/serve_model.py --model-id qwen-coder \
    --model-path models/qwen-coder/qwen2.5-coder-3b-instruct-q4_k_m.gguf \
    --port 8002 --n-gpu-layers 99 --n-ctx 2048

# Terminal 2: vision (CPU first; CUDA pending validation)
python scripts/serve_model.py --model-id qwen-vision \
    --model-path models/qwen-vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf \
    --mmproj models/qwen-vision/mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf \
    --chat-format qwen2-vl --port 8003

# Terminal 3: backend
cd backend
PYTHONPATH=. uvicorn app.main:app --reload --port 8000

# Terminal 4: frontend
cd frontend
npm install
npm run dev
```

If `qwen-vision` weights are not present, the vision server will fail
to start and `/api/vision/analyze` will return 503; the frontend
renders a "VISION ANALYSIS UNAVAILABLE" panel for the user.

### Containerised (Docker Compose)

```bash
cd infra
docker-compose -f docker-compose.yml --profile gpu up -d   # with GPU services
docker-compose -f docker-compose.cpu.yml up -d             # CPU only
```

The compose `gpu` profile launches the three llama.cpp server
containers. The `cpu` profile assumes bare-metal `serve_model.py`
processes for the local model servers.

### Ingestion subsystem (Phase 1 + 1.5)

```bash
cd backend/ingestion
uv run python -m app.main serve      # serves the FastAPI ingestion service + static frontend
uv run python -m app.main ingest --project <path>
```

See `backend/ingestion/README.md` for the full pipeline.

---

## Project layout

```
Sovereign_AI/
├── README.md                 # this file
├── Better_plan.md            # full architecture spec + current status table
├── Better_plan.pdf           # architecture spec (PDF)
├── Problem_Statemen.md       # problem statement
├── final_frontend_gpt.md     # frontend design notes
│
├── backend/                  # FastAPI + LangGraph application
│   ├── app/                  # production FastAPI package (routes, RAG, models, security)
│   ├── agent/                # standalone maintenance agent (LangGraph) + coder subpackage
│   │   └── security/         # NetworkGuard
│   ├── rag/                  # standalone RAG package (Qdrant + bm25s)
│   ├── ingestion/            # Phase 1 + 1.5 ingestion subsystem
│   ├── tests/                # pytest suite (~120 tests)
│   └── scripts/              # internal E2E helpers
│
├── frontend/                 # React + Vite + Tailwind SPA
│   └── src/
│       ├── pages/            # Workbench, NetworkMonitor, VisionResult, …
│       ├── lib/api/          # typed Axios client (control + inference timeouts)
│       └── lib/utils.ts      # isVisionUnavailable() honest disclosure helper
│
├── infra/                    # Docker Compose + .env.example
│
├── scripts/                  # local model launcher + demo scripts
│   └── serve_model.py        # llama-cpp-python FastAPI wrapper
│
├── models/                   # local GGUF weights (gitignored)
│   ├── qwen-coder/           # Qwen2.5-Coder-3B-Instruct Q4_K_M
│   └── qwen-vision/          # Qwen2.5-VL-3B-Instruct + mmproj
│
├── data/
│   ├── rag/                  # Qdrant (393 chunks) + BM25 index
│   ├── pid_analysis/         # P&ID analysis outputs
│   └── synthetic/            # synthetic plant dataset
│
├── demo-data/                # demo documents for ingestion
├── uploads/                  # runtime uploads
├── PID_Dataset/              # P&ID image classification dataset
├── prerequistes/             # per-component setup notes
├── reports/                  # per-phase validation write-ups
└── _rollback/                # Phase 11.4 CUDA build artifacts + CPU fallback wheel
```

---

## Testing

```bash
# Backend integration tests (app + agent)
cd backend
pytest tests/ -v

# RAG-specific tests
cd backend
pytest rag/tests/ -v

# Ingestion subsystem tests
cd backend/ingestion
pytest tests/ -v

# Frontend unit tests
cd frontend
npm test

# Lint & type check
cd backend
ruff check .
mypy app/
```

The backend test suite covers NetworkGuard (28 parametrized cases
including link-local, RFC5737, RFC2544, IPv6 link-local, IPv6 ULA,
cloud-metadata, and hostname-lookalike rejection), the router
(16 cases), the coder sandbox (29 cases), vision honesty (10 cases),
Piston boundary enforcement (10 cases), and the Phase 10.4
inference-reliability regressions (12 cases).

---

## Known limitations

- **General LLM weights are not provisioned.** The endpoint, registry
  entry, router path, and `/api/system/status` are all in place; a
  small Qwen 2.5 3B Instruct GGUF still needs to be downloaded into
  `models/qwen-general/`.
- **Vision CUDA has not been validated.** The `n_gpu_layers` flag
  flows from `serve_model.py` into the underlying `Llama(...)`
  constructor, but the VLM path on RTX 4050 has not been benchmarked
  yet. Treat vision inference as CPU-only until that validation
  completes.
- **GPU concurrency is not validated.** The deployment plan loads
  one GGUF at a time on the 6 GB RTX 4050 (sequential loading via
  per-model servers); concurrent multi-model GPU inference has not
  been measured.
- **PaddleOCR is in a separate environment.** The Qdrant client pins
  `protobuf<6`, which conflicts with `paddlepaddle>=2.5`. PaddleOCR
  is installed and exercised in its own environment per
  `prerequistes/PaddleOCR.md`; it is not imported in the
  `backend/app` path. The full multimodal pipeline is exercised in
  Phase 9+ via the local VLM.
- **Single-host only.** The compose stack assumes one host per
  deployment; the router does not fan out across nodes.

---

## Roadmap

| Area                   | Current state                            | Next                                              |
|------------------------|------------------------------------------|---------------------------------------------------|
| Backend API            | FastAPI + LangGraph, all routes live     | Maintain                                          |
| RAG (Qdrant + BM25)    | 393 chunks, weighted hybrid, citations   | Re-rank tuning                                    |
| NetworkGuard           | explicit trusted-local CIDRs            | Maintain                                          |
| Coder (Qwen2.5-Coder)  | CPU + CUDA on RTX 4050 validated         | (optional) larger coder / context experiments     |
| Vision (Qwen2.5-VL)    | CPU validated                            | **CUDA validation on RTX 4050 (P11.5/12)**       |
| General LLM            | router + endpoint reserved, weights absent | **Provision Qwen 2.5 3B Instruct GGUF**         |
| GPU concurrency        | one model at a time (validated)          | None planned (single 6 GB GPU)                    |
| E2E harness            | per-phase suites + agent E2E             | Expand vision CUDA E2E once vision-GPU validated  |
| 4 golden demos         | inspection-approval, data-analysis, multimodal, correspondence-search | Re-run all 4 against the CUDA coder |

Longer-term: rotate the model set, evaluate a reranker swap,
and consider Windows Long Path support for in-place CUDA rebuilds.

---

## See also

- `Better_plan.md` — full architecture specification with the current
  status table for every roadmap item (COMPLETED / IN PROGRESS /
  NEXT / BLOCKED / DEFERRED / OBSOLETE).
- `reports/` — per-phase validation write-ups
  (Phases 5–8, plus the Phase 11.4 CUDA build report).
- `prerequistes/` — per-component setup and reference notes.
- `_rollback/llama_cpp_python-0.3.35-cpu-py3-none-win_amd64.whl` —
  known-good CPU fallback wheel if the CUDA build ever needs to be
  reverted.
