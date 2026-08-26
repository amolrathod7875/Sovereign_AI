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

## Architecture

- **Frontend**: React + TypeScript + Tailwind
- **Backend**: Python + FastAPI + LangGraph
- **Model Serving**: vLLM
- **Vector DB**: Qdrant
- **Relational DB**: PostgreSQL
- **Sandbox**: Piston + Docker

## API Endpoints

- `POST /api/chat` - Chat with streaming
- `POST /api/agent/run` - Full agent workflow
- `POST /api/documents/upload` - Upload document
- `POST /api/documents/ingest` - Ingest document
- `GET /api/documents` - List documents
- `POST /api/rag/search` - Search knowledge base
- `GET /api/models` - List models
- `POST /api/sandbox/execute` - Execute code in sandbox
- `GET /api/system/status` - System health
- `GET /api/network/monitor` - Network monitor SSE

## Demo

See `Better_plan.md` for full architecture specification.
