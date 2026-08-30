# Phase 5D — Architecture Audit (Consolidation Map)

Scope: map every existing capability in `Sovereign_AI` to ONE authoritative
production execution path. No new capabilities are built in 5D.

## 1. Runtime / entry points

| Concern | Authoritative | Duplicate / dead | Disposition |
|---|---|---|---|
| FastAPI backend | `backend/app/main.py` (lifespan → `init_db` + `init_qdrant`) | `backend/ingestion/app/api.py` (separate FastAPI app) | Keep `backend/app`; `backend/ingestion` is an **unused separate contribution** (see §5) |
| Frontend | `frontend/` (React/Vite/TS) | `backend/ingestion/frontend/` | Keep `frontend/` |

## 2. Orchestration

| Concern | Authoritative | Duplicate / dead | Disposition |
|---|---|---|---|
| LangGraph agent | `backend/agent/` (`graph.py` + `run.py` + `nodes/*` + `tools/*` + `security/netguard.py`) | `backend/app/agents/graph.py` | **`app/agents` is dead code** — it imports `app.rag.retrieval` (mock) and is not mounted by `app/api`. The mounted agent route (`app/api/agent.py`) calls `agent.run.run_agent`, i.e. `backend/agent`. Delete/ignore `app/agents`. |
| Capability router | `backend/app/models/router.py` (capability-based, sovereignty-enforced, Phase 5C-2) | (none) | Authoritative. Used by `/api/models/route` and by `agent/run.py` for explainability |
| Model registry | `backend/app/models/registry.py` + `app/models/client.py` | (none) | Authoritative |

## 3. Knowledge / RAG

| Concern | Authoritative | Duplicate / dead | Disposition |
|---|---|---|---|
| Hybrid retriever | `backend/rag/retrieval/hybrid.py` (embedded Qdrant `path=`, `bm25s`, `sentence-transformers` `LocalEmbedder`, collection `sovereign_knowledge`) | `backend/app/rag/{dense,sparse,reranker,qdrant}.py` (server Qdrant `sovereign_rag`, **mock random embeddings in `dense.py`**, in-memory BM25, placeholder reranker) | **`app/rag` is a dead/placeholder path** — not used by the agent. Keep `backend/rag` |
| Ingestion | `backend/rag/ingestion/ingest.py` (`run_ingest` indexes the 10 synthetic docs into embedded Qdrant + BM25) | `backend/app/rag/ingest.py` (uses mock dense), `backend/ingestion/` | Keep `backend/rag/ingestion`; others unused |
| Parser | `backend/rag/ingestion/parsers.py` | `backend/app/rag/parser.py`, `backend/ingestion/app/parsers.py` (uses `pypdf`, which is NOT installed) | Keep `backend/rag/ingestion/parsers.py` |

## 4. Model servers / tools

| Concern | Authoritative | Notes |
|---|---|---|
| Coder | `agent/coder/model.py` → `localhost:8002` (Qwen2.5-Coder-3B GGUF, `scripts/serve_model.py`) | Weights present |
| Vision | `agent/tools/vision.py` → `localhost:8003` (Qwen2.5-VL-3B GGUF + mmproj) | Weights present |
| General reasoning | `registry.general` → `localhost:8001` (Qwen2.5-3B-Instruct) | **Weights NOT on disk** — router correctly reports "local model unavailable"; no fallback to external |
| OCR | `app/rag/ocr.py` (PaddleOCR) | Only real OCR; agent vision path uses the VLM instead |

## 5. `backend/ingestion/` — separate, NOT integrated

- It is an independent FastAPI app (`uv.lock`, own `pyproject.toml`) with
  `parsers.py` that label outputs `"docling_simulated"` / `"unstructured_simulated"`
  (i.e. parsing is **simulated**, not real OCR/parse).
- It writes JSON manifests to `backend/ingestion/data/{incoming,raw,processed}` and
  does **not** write to Qdrant/BM25 and does **not** integrate with `backend/rag`.
- Decision (5D, OPTION A): keep `backend/rag` as the authoritative ingestion path;
  do **not** run two ingestion systems. `backend/ingestion` is documented as an
  unused contribution and left untouched.

## 6. Network sovereignty

- `agent/security/netguard.py` (NetworkGuard + socket-probe guard) wraps every agent
  run. `app/api/network.py` records events. `system.py` reports `external_api_calls`
  honestly. Agent runs return `external_calls == 0` (verified).
