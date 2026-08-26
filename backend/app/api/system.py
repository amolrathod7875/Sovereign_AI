from fastapi import APIRouter
import time
import os

from app.schemas import SystemStatus
from app.config import settings

_start_time = time.time()

router = APIRouter()


@router.get("/status")
async def get_system_status() -> SystemStatus:
    gpu_info = get_gpu_info()

    services = {
        "vllm_general": {"status": "unknown", "model": "Qwen2.5-3B-Instruct"},
        "vllm_coder": {"status": "unknown", "model": "Qwen2.5-Coder-3B"},
        "vllm_vision": {"status": "unknown", "model": "Qwen-VL-3B"},
        "qdrant": {"status": "unknown"},
        "postgres": {"status": "unknown"},
        "piston": {"status": "unknown"},
    }

    for service in services:
        services[service]["status"] = "online"

    return SystemStatus(
        sovereign=settings.SOVEREIGN_MODE,
        gpu=gpu_info,
        services=services,
        uptime_seconds=int(time.time() - _start_time),
        external_api_calls=0,
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
                    "memory_used_gb": int(parts[1].strip().split()[0]) / 1024,
                    "memory_total_gb": int(parts[2].strip().split()[0]) / 1024,
                }
    except Exception:
        pass

    return {
        "name": "Unknown GPU",
        "memory_used_gb": 0,
        "memory_total_gb": 0,
    }


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "sovereign_mode": settings.SOVEREIGN_MODE,
        "uptime_seconds": int(time.time() - _start_time),
    }
