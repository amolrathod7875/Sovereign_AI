"""System / health surface.

Phase 6 integration fix: ``GET /api/system/status`` previously set every service to
``"online"`` unconditionally (``for service in services: services[service]["status"] =
"online"``) and hard-coded ``external_api_calls = 0``. The frontend must not display
invented availability (Phase 6 Part 5), so the status is now *probed*:

* local model servers  -> TCP/HTTP probe of the registered loopback ``/v1/models``
* local model weights  -> real on-disk GGUF discovery under ``models/``
* embedded Qdrant/BM25 -> real index paths used by the authoritative ``backend/rag``
* PostgreSQL           -> real async engine connection attempt
* agent / router /
  NetworkGuard         -> real importability of the authoritative modules
* external_api_calls   -> summed from NetworkGuard results of real runs + blocked
                          connection events (never asserted as 0)

No new service, model client or router is introduced: everything is read from the
existing authoritative components.
"""
from fastapi import APIRouter
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from app.schemas import SystemStatus
from app.config import settings

logger = logging.getLogger(__name__)

_start_time = time.time()

router = APIRouter()

# Honest status vocabulary exposed to the UI.
ONLINE = "ONLINE"
OFFLINE = "OFFLINE"
UNAVAILABLE = "UNAVAILABLE"
NOT_CONFIGURED = "NOT CONFIGURED"

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = REPO_ROOT / "models"

_PROBE_TIMEOUT = float(os.environ.get("SYSTEM_PROBE_TIMEOUT", "1.5"))

# model registry id -> directory under models/ that would hold its GGUF weights
_WEIGHT_DIRS = {
    "qwen-coder": ["qwen-coder"],
    "vision": ["qwen-vision"],
    "general": ["qwen-general", "general", "qwen2.5-3b-instruct"],
}


def _weights_present(model_id: str) -> bool:
    """True if a GGUF weight file for ``model_id`` actually exists on this disk."""
    for d in _WEIGHT_DIRS.get(model_id, []):
        p = MODELS_DIR / d
        if p.is_dir() and any(p.glob("*.gguf")):
            return True
    return False


def _probe_model_server(endpoint: str) -> bool:
    """GET ``{endpoint}/models`` on a loopback endpoint. Never raises."""
    if not endpoint:
        return False
    try:
        with httpx.Client(timeout=_PROBE_TIMEOUT) as c:
            return c.get(f"{endpoint.rstrip('/')}/models").status_code == 200
    except Exception:
        return False


def _model_component(model_id: str, label: str) -> Dict:
    from app.models.registry import get_model, is_local_endpoint

    m = get_model(model_id) or {}
    endpoint = m.get("endpoint")
    if not endpoint:
        return {"id": model_id, "name": label, "status": NOT_CONFIGURED,
                "detail": "no endpoint registered", "endpoint": None, "local": True}
    if not is_local_endpoint(endpoint):
        return {"id": model_id, "name": label, "status": NOT_CONFIGURED,
                "detail": f"endpoint {endpoint} is not loopback/private",
                "endpoint": endpoint, "local": False}

    reachable = _probe_model_server(endpoint)
    if reachable:
        return {"id": model_id, "name": m.get("name", label), "status": ONLINE,
                "detail": f"serving on {endpoint}", "endpoint": endpoint, "local": True}
    if not _weights_present(model_id):
        return {"id": model_id, "name": m.get("name", label), "status": UNAVAILABLE,
                "detail": (f"GGUF weights not present on this host and no server on "
                           f"{endpoint}"),
                "endpoint": endpoint, "local": True}
    return {"id": model_id, "name": m.get("name", label), "status": OFFLINE,
            "detail": f"weights present but no server responding on {endpoint}",
            "endpoint": endpoint, "local": True}


def _import_component(cid: str, name: str, module: str, attr: str) -> Dict:
    try:
        mod = __import__(module, fromlist=[attr])
        getattr(mod, attr)
        return {"id": cid, "name": name, "status": ONLINE,
                "detail": f"{module}.{attr} loaded", "endpoint": None, "local": True}
    except Exception as e:
        return {"id": cid, "name": name, "status": UNAVAILABLE,
                "detail": f"{module} import failed: {e}", "endpoint": None, "local": True}


def _qdrant_component() -> Dict:
    """Authoritative RAG vector store = embedded Qdrant used by ``backend/rag``."""
    try:
        from rag import config as rag_config

        path = Path(rag_config.QDRANT_PATH)
        collection = rag_config.COLLECTION_NAME
    except Exception as e:
        return {"id": "qdrant", "name": "Qdrant (embedded)", "status": UNAVAILABLE,
                "detail": f"rag config unavailable: {e}", "endpoint": None, "local": True}

    server = None
    try:
        with httpx.Client(timeout=_PROBE_TIMEOUT) as c:
            server = c.get(f"{settings.QDRANT_URL.rstrip('/')}/collections").status_code == 200
    except Exception:
        server = False

    if path.is_dir() and any(path.iterdir()):
        detail = f"embedded index at {path} (collection '{collection}')"
        detail += "; server on %s: %s" % (settings.QDRANT_URL, "up" if server else "not running")
        return {"id": "qdrant", "name": "Qdrant (embedded)", "status": ONLINE,
                "detail": detail, "endpoint": str(path), "local": True}
    return {"id": "qdrant", "name": "Qdrant (embedded)", "status": UNAVAILABLE,
            "detail": f"no embedded index at {path}; run rag ingestion first",
            "endpoint": str(path), "local": True}


def _bm25_component() -> Dict:
    try:
        from rag import config as rag_config

        idx = Path(rag_config.BM25_DIR) / "bm25_index"
        corpus = Path(rag_config.BM25_DIR) / "corpus.json"
    except Exception as e:
        return {"id": "bm25", "name": "BM25", "status": UNAVAILABLE,
                "detail": f"rag config unavailable: {e}", "endpoint": None, "local": True}
    if idx.exists() and corpus.exists():
        n = None
        try:
            import json

            with open(corpus, encoding="utf-8") as f:
                n = len(json.load(f).get("order", []))
        except Exception:
            pass
        detail = f"lexical index at {idx}"
        if n is not None:
            detail += f" ({n} chunks)"
        return {"id": "bm25", "name": "BM25", "status": ONLINE, "detail": detail,
                "endpoint": str(idx), "local": True}
    return {"id": "bm25", "name": "BM25", "status": UNAVAILABLE,
            "detail": f"no BM25 index at {idx}; run rag ingestion first",
            "endpoint": str(idx), "local": True}


async def _postgres_component() -> Dict:
    from app.storage.postgres import engine

    if engine is None:
        return {"id": "postgres", "name": "PostgreSQL", "status": NOT_CONFIGURED,
                "detail": "async engine could not be created from POSTGRES_URL",
                "endpoint": None, "local": True}
    try:
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"id": "postgres", "name": "PostgreSQL", "status": ONLINE,
                "detail": "connection OK", "endpoint": None, "local": True}
    except Exception as e:
        return {"id": "postgres", "name": "PostgreSQL", "status": OFFLINE,
                "detail": f"not reachable: {type(e).__name__}", "endpoint": None,
                "local": True}


def _external_call_stats() -> Dict[str, int]:
    """Real external-call accounting from NetworkGuard results and blocked events."""
    external = 0
    runs = 0
    for module in ("app.api.agent", "app.api.coder"):
        try:
            mod = __import__(module, fromlist=["_RUNS"])
            for result in getattr(mod, "_RUNS", {}).values():
                runs += 1
                if isinstance(result, dict):
                    external += int(result.get("external_calls") or 0)
        except Exception:
            continue
    blocked = 0
    try:
        from app.api.network import _events

        blocked = len([e for e in _events if getattr(e, "action", "") == "BLOCKED"])
    except Exception:
        blocked = 0
    return {"external_api_calls": external, "blocked_connections": blocked,
            "runs_observed": runs}


def build_components(postgres: Optional[Dict] = None) -> List[Dict]:
    components: List[Dict] = [
        {"id": "fastapi", "name": "FastAPI", "status": ONLINE,
         "detail": "serving this request", "endpoint": "/", "local": True},
        _import_component("agent", "Agent (LangGraph)", "agent.run", "run_agent_task"),
        _import_component("router", "Model Router", "app.models.router", "route"),
        _model_component("qwen-coder", "Qwen Coder"),
        _model_component("vision", "Qwen-VL"),
        _model_component("general", "General Model"),
        _qdrant_component(),
        _bm25_component(),
        postgres or {"id": "postgres", "name": "PostgreSQL", "status": UNAVAILABLE,
                     "detail": "not probed", "endpoint": None, "local": True},
        _import_component("networkguard", "NetworkGuard", "agent.security.netguard",
                          "no_network"),
    ]
    return components


@router.get("/status")
async def get_system_status() -> SystemStatus:
    gpu_info = get_gpu_info()
    components = build_components(await _postgres_component())
    stats = _external_call_stats()

    # Backwards-compatible flat map (now honest, no longer forced to "online").
    services = {
        c["id"]: {"status": c["status"], "name": c["name"], "detail": c["detail"]}
        for c in components
    }

    return SystemStatus(
        sovereign=settings.SOVEREIGN_MODE,
        gpu=gpu_info,
        services=services,
        components=components,
        uptime_seconds=int(time.time() - _start_time),
        external_api_calls=stats["external_api_calls"],
        blocked_connections=stats["blocked_connections"],
    )


def get_gpu_info():
    try:
        import subprocess

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            if len(parts) >= 3:
                return {
                    "name": parts[0].strip(),
                    "memory_used_gb": round(int(parts[1].strip().split()[0]) / 1024, 2),
                    "memory_total_gb": round(int(parts[2].strip().split()[0]) / 1024, 2),
                }
    except Exception:
        pass

    return {
        "name": None,
        "memory_used_gb": None,
        "memory_total_gb": None,
    }


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "sovereign_mode": settings.SOVEREIGN_MODE,
        "uptime_seconds": int(time.time() - _start_time),
    }
