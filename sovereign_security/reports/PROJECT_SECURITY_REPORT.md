# Project Security Report

## 1. Project Structure
The repository is split into various operational directories:
- `backend/`: Hosts FastAPI endpoints, LangGraph agent definitions, and RAG components.
- `frontend/`: Vite-based React application.
- `infra/`: Docker compose configuration for running sandbox (Piston), databases (Postgres, Qdrant).
- `uploads/`: Untrusted boundary for file uploads.

## 2. Entry Points
- API server: `backend/app/main.py`
- Agent Task execution: `backend/agent/run.py`
- RAG ingestion pipeline: `backend/rag/run_ingest.py`

## 3. Endpoints & Boundaries
- Model Endpoints: `http://localhost:8002/v1`, `http://localhost:8003/v1`
- Subprocess execution/sandbox: Uses `piston` (`http://piston:2000`) and has some local network socket guardrails described in the architecture.
- File system access: Read-only access to specific directories for vision model; writes limited to `data/outputs/` and `data/artifacts/`.

## 4. Trust Boundaries
- **Untrusted File Uploads**: Input vectors via `uploads/` could contain malicious prompts embedded in OCR/PDF.
- **RAG Retrieval**: Retrieved chunks from `Qdrant` DB may introduce context-poisoning attacks.
- **Piston Sandbox**: External execution is restricted via Piston, but requires strict validation of input and output schemas.
- **External Network Calls**: There are multiple local HTTP endpoints (`httpx`). They are strictly limited to `localhost` in production.

## 5. Known Secrets
- **Database Connection**: Hardcoded test string in `backend/app/config.py` (`REDACTED`).

## 6. Security Posture
- Network guard is already implemented in `agent/run.py` but the architecture needs formal, decoupled OWASP-based wrappers (Input, Output, Prompt Guards) to make these enforcements modular.
