from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.api import (
    chat,
    documents,
    rag,
    models,
    sandbox,
    executions,
    network,
    system,
    agent,
    coder,
    vision,
    artifacts,
)
from app.storage.postgres import init_db
from app.storage.qdrant import init_qdrant

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Sovereign AI backend...")
    await init_db()
    await init_qdrant()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down Sovereign AI backend...")


app = FastAPI(
    title="Sovereign AI",
    description="Self-hosted, local-only AI workbench for confidential industrial work",
    version="1.0.0",
    lifespan=lifespan,
)

# Sovereignty + security: allow ONLY the explicit local development origins the
# frontend is served from (see settings.CORS_ALLOW_ORIGINS). A wildcard "*" was
# previously configured, which allowed any page in the browser to call the local
# backend; that is now removed (Phase 6 Part 16). The browser only ever talks to
# this local backend, and no credentials/secrets are exposed to it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
    expose_headers=["Content-Disposition"],
)

# NOTE: `chat` must not declare /agent/run — the authoritative agent router below
# owns that path (see app/api/chat.py header).
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(rag.router, prefix="/api/rag", tags=["rag"])
app.include_router(models.router, prefix="/api/models", tags=["models"])
app.include_router(sandbox.router, prefix="/api/sandbox", tags=["sandbox"])
app.include_router(executions.router, prefix="/api/executions", tags=["executions"])
app.include_router(network.router, prefix="/api/network", tags=["network"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(coder.router, prefix="/api/coder", tags=["coder"])
app.include_router(vision.router, prefix="/api/vision", tags=["vision"])
app.include_router(artifacts.router, prefix="/api/artifacts", tags=["artifacts"])


@app.get("/")
async def root():
    return {
        "name": "Sovereign AI",
        "version": "1.0.0",
        "status": "running",
        "sovereign_mode": settings.SOVEREIGN_MODE,
    }
