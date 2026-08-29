# Sovereign AI

Self-hosted, air-gapped AI workbench for confidential industrial work.

## Quick Start

### With GPU Support

```bash
cd infra
docker-compose -f docker-compose.yml up -d
```

### CPU Only (No GPU)

```bash
cd infra
docker-compose -f docker-compose.cpu.yml up -d
```

### Local Development (without Docker)

**Backend**

```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=/app uvicorn app.main:app --reload --port 8000
```

**Frontend**

```bash
cd frontend
npm install        # or: pnpm install
npm run dev        # Vite dev server on http://localhost:3000
```

> Copy `infra/.env.example` to `backend/.env` and adjust values for local runs
> without containers.

## Architecture

- **Frontend**: React + TypeScript + Vite + Tailwind CSS
- **Backend**: Python 3.11 + FastAPI + LangGraph + LangChain
- **Model Serving**: vLLM (GPU) or llama.cpp/GGUF (CPU)
- **Vector DB**: Qdrant (dense) + BM25 sparse retrieval
- **Relational DB**: PostgreSQL
- **Sandbox**: Piston + Docker
- **OCR**: PaddleOCR + PyMuPDF

## Services (Docker Compose)

| Service          | Description                          | Port |
|------------------|--------------------------------------|------|
| `frontend`       | React UI (Vite)                      | 3000 |
| `backend`        | FastAPI application                  | 8000 |
| `postgres`       | PostgreSQL 16                        | 5432 |
| `qdrant`         | Qdrant vector store                  | 6333/6334 |
| `piston`         | Code execution sandbox               | 2000 |
| `vllm-general`   | General-purpose LLM                  | 8001 |
| `vllm-coder`     | Coder LLM                            | 8002 |
| `vllm-vision`    | Vision LLM                           | 8003 |

> vLLM services use the `gpu` Docker profile and require NVIDIA GPU support.

## API Endpoints

| Method | Path                         | Description                  |
|--------|------------------------------|------------------------------|
| `POST` | `/api/chat`                  | Chat with streaming          |
| `POST` | `/api/agent/run`             | Run full agent workflow      |
| `GET`  | `/api/agent/runs/{id}`       | Fetch stored run result      |
| `POST` | `/api/documents/upload`      | Upload a document            |
| `POST` | `/api/documents/ingest`      | Ingest a document            |
| `GET`  | `/api/documents`             | List documents               |
| `POST` | `/api/rag/search`            | Search the knowledge base    |
| `GET`  | `/api/models`                | List available models        |
| `POST` | `/api/sandbox/execute`       | Execute code in sandbox      |
| `GET`  | `/api/system/status`         | System health                |
| `GET`  | `/api/network/monitor`       | Network monitor (SSE)        |

## File Structure

```
Sovereign_AI/
├── readme.md                  # Project overview
├── README.md                  # This file
├── Better_plan.md             # Full architecture specification
├── Better_plan.pdf            # Architecture spec (PDF)
├── Problem_Statemen.md        # Problem statement
├── PID_analysis_report.md     # PID analysis results report
├── final_frontend_gpt.md      # Frontend design notes
├── analyze_pid.py             # PID image analysis script
├── fix_pid_naming.py          # PID naming utility
├── gen_report.py              # Report generation script
├── gen_synthetic.py           # Synthetic data generation
├── pid_pipeline.py            # PID processing pipeline
├── verify_pid.py              # PID verification script
├── test_qwen_coder.py         # Qwen coder test
├── test_qwen_cv.py            # Qwen CV test
├── test_qwen_cv_pid.py        # Qwen CV PID test
├── test_qwen_cv_server.py     # Qwen CV server test
│
├── backend/                   # FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/                   # Main application package
│   │   ├── main.py            # FastAPI entry point, router registration
│   │   ├── config.py          # Pydantic settings (.env loader)
│   │   ├── __init__.py
│   │   ├── agents/            # Maintenance agent (LangGraph)
│   │   │   ├── graph.py       # Agent workflow graph
│   │   │   ├── planner.py     # Task planning
│   │   │   ├── policies.py    # Safety / approval policies
│   │   │   ├── state.py       # Agent state schema
│   │   │   └── __init__.py
│   │   ├── api/               # API route handlers
│   │   │   ├── agent.py       # POST /api/agent/run
│   │   │   ├── chat.py        # POST /api/chat (streaming)
│   │   │   ├── documents.py   # /api/documents (upload, ingest, list)
│   │   │   ├── executions.py  # /api/executions
│   │   │   ├── models.py      # GET /api/models
│   │   │   ├── network.py     # GET /api/network/monitor (SSE)
│   │   │   ├── rag.py         # POST /api/rag/search
│   │   │   ├── sandbox.py     # POST /api/sandbox/execute
│   │   │   ├── system.py      # GET /api/system/status
│   │   │   └── __init__.py
│   │   ├── models/            # LLM client & routing
│   │   │   ├── client.py      # OpenAI-compatible client
│   │   │   ├── registry.py    # Model registry
│   │   │   ├── router.py      # Request routing (general/coder/vision)
│   │   │   └── __init__.py
│   │   ├── rag/               # RAG pipeline
│   │   │   ├── chunker.py     # Text chunking
│   │   │   ├── citations.py   # Citation extraction
│   │   │   ├── correspondence.py
│   │   │   ├── dense.py       # Dense (vector) retrieval
│   │   │   ├── fusion.py      # Reciprocal rank fusion
│   │   │   ├── ingest.py
│   │   │   ├── ocr.py         # PaddleOCR
│   │   │   ├── parser.py      # Document parsing
│   │   │   ├── reranker.py
│   │   │   ├── retrieval.py
│   │   │   ├── sparse.py      # BM25 retrieval
│   │   │   └── __init__.py
│   │   ├── schemas/           # Pydantic DTOs
│   │   │   ├── api.py
│   │   │   └── __init__.py
│   │   ├── security/          # Security & monitoring
│   │   │   ├── audit.py
│   │   │   ├── network_monitor.py
│   │   │   ├── sandbox_policy.py
│   │   │   └── __init__.py
│   │   ├── storage/           # Persistence layer
│   │   │   ├── postgres.py    # DB init + helpers
│   │   │   ├── qdrant.py      # Vector DB init + helpers
│   │   │   └── __init__.py
│   │   └── tools/             # Agent tools
│   │       ├── docx_tool.py
│   │       ├── pptx_tool.py
│   │       ├── python_tool.py
│   │       ├── rag_tool.py
│   │       ├── spreadsheet_tool.py
│   │       └── __init__.py
│   ├── agent/                  # (Legacy / standalone) agent package
│   │   ├── config.py
│   │   ├── graph.py
│   │   ├── run.py
│   │   ├── state.py
│   │   ├── utils.py
│   │   ├── __init__.py
│   │   ├── evaluation/
│   │   │   ├── evaluate.py
│   │   │   └── __init__.py
│   │   ├── nodes/
│   │   │   ├── analyze.py
│   │   │   ├── calculate.py
│   │   │   ├── calculate_route.py
│   │   │   ├── decide.py
│   │   │   ├── generate.py
│   │   │   ├── plan.py
│   │   │   ├── retrieve.py
│   │   │   ├── synthesize.py
│   │   │   ├── verify.py
│   │   │   └── __init__.py
│   │   ├── prompts/
│   │   │   └── planner.py
│   │   ├── security/
│   │   │   ├── netguard.py
│   │   │   └── __init__.py
│   │   └── tools/
│   │       ├── analyze_csv.py
│   │       ├── create_docx.py
│   │       ├── python_execute.py
│   │       ├── read_document.py
│   │       ├── search_kb.py
│   │       └── __init__.py
│   └── tests/                  # Backend tests
│
├── frontend/                   # React frontend
│   ├── Dockerfile
│   ├── index.html
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── index.css
│       ├── components/
│       │   └── layout/
│       │       └── Layout.tsx
│       └── pages/
│           ├── Artifacts.tsx
│           ├── Dashboard.tsx
│           ├── ExecutionTrace.tsx
│           ├── KnowledgeBase.tsx
│           ├── ModelRegistry.tsx
│           ├── NetworkMonitor.tsx
│           ├── System.tsx
│           └── Workbench.tsx
│
├── infra/                      # Docker Compose & infra config
│   ├── docker-compose.yml       # GPU-enabled stack
│   ├── docker-compose.cpu.yml   # CPU-only stack
│   └── .env.example
│
├── scripts/
│   └── serve_model.py          # Local model serving helper
│
├── models/                     # Local GGUF model weights (gitignored)
│   ├── qwen-coder/
│   └── qwen-vision/
│
├── data/                       # Runtime / analysis data
│   ├── outputs/                # Generated artifact outputs
│   ├── pid_analysis/           # PID image analysis
│   │   ├── json/                # Parsed PID JSON results
│   │   ├── raw/                 # Raw PID text files
│   │   ├── registry/            # Equipment / instrument / stream registries
│   │   ├── reports/             # Quality / selection / verification reports
│   │   └── verify_crops/        # Cropped verification images
│   ├── rag/                    # RAG indices
│   │   ├── bm25/                # BM25 sparse index + corpus
│   │   └── qdrant_db/           # Qdrant on-disk storage
│   ├── synthetic/              # Synthetic dataset
│   │   ├── assets/              # Generated documents, images, CSVs
│   │   ├── metadata/
│   │   └── plant/
│   └── synthetic_assets/...    # (see data/synthetic)
│
├── demo-data/                  # Demo documents for ingestion
│   ├── correspondence/
│   ├── csv/
│   ├── drawings/
│   ├── manuals/
│   ├── reports/
│   └── sops/
│
├── uploads/                    # Uploaded files (runtime)
│
├── PID_Dataset/                # PID image classification dataset
│   ├── 0__raw_data/
│   │   ├── labels/
│   │   └── sheets/
│   └── 1__processed_data/
│       ├── crops/
│       └── labels/
│
├── prerequistes/               # Setup & reference docs
│   ├── BM25.md
│   ├── Embeddings.md
│   ├── PaddleOCR.md
│   ├── Piston.md
│   ├── PostgreSQL.md
│   ├── PyMuPDF.md
│   ├── Qdrant.md
│   ├── Qwen2.5-coder-Instruct.md
│   ├── Qwen2.5-VL-3B-Instruct.md
│   └── RRF.md
│
└── reports/                    # Evaluation & analysis reports
    ├── agent_evaluation.md
    └── rag_evaluation.md
```

## Components

### Backend (`backend/`)

Two parallel code trees coexist:

- **`backend/app/`** — the production FastAPI application. This is the entry
  point used by Docker (`app.main:app`). It contains the API routes, RAG
  pipeline, model client/router, storage layer, and security modules.
- **`backend/agent/`** — a standalone maintenance agent built on LangGraph.
  It is invoked by the `/api/agent/run` endpoint via lazy import. It includes
  planning, retrieval, calculation, synthesis, and verification nodes.

The RAG ingestion pipeline lives under `backend/rag/` (chunking, parsing,
OCR, dense/sparse indexing) and is driven by `backend/rag/run_ingest.py`.

### Frontend (`frontend/`)

React + TypeScript + Vite single-page application with Tailwind CSS. Pages cover
the workbench chat, dashboard, knowledge base, model registry, execution trace,
network monitor, system status, and artifacts.

## Demo

See `Better_plan.md` for the full architecture specification.

## Prerequisites

Setup and reference documentation for each service is in `prerequistes/`:

| File                        | Purpose                        |
|-----------------------------|--------------------------------|
| `prerequistes/Piston.md`    | Code sandbox setup             |
| `prerequistes/Qdrant.md`    | Vector DB setup                |
| `prerequistes/PostgreSQL.md`| Relational DB setup            |
| `prerequistes/BM25.md`      | Sparse retrieval               |
| `prerequistes/Embeddings.md`| Embedding model setup          |
| `prerequistes/PaddleOCR.md` | OCR setup                      |
| `prerequistes/PyMuPDF.md`   | PDF parsing                    |
| `prerequistes/RRF.md`       | Reciprocal rank fusion         |
| `prerequistes/Qwen2.5-coder-Instruct.md` | Coder model setup |
| `prerequistes/Qwen2.5-VL-3B-Instruct.md` | Vision model setup |

## Testing

```bash
# Backend unit tests
cd backend
python -m pytest rag/tests/ -v

# Lint & type check
ruff check .
mypy app/
```
