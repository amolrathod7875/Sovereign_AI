"""FastAPI integration for the local vision tool.

Reuses the SINGLE vision tool implemented in ``agent.tools.vision`` (the same one
the LangGraph agent uses), so there is one tool system, not a parallel one.

Exposes:
  POST /api/vision/analyze   -> analyze an approved local image/PDF with the local VLM

Phase 6 change (integration only): the call runs in a worker thread wrapped in the
EXISTING ``agent.security.netguard`` guard, so (a) a 60-100 s CPU-bound VLM call no
longer blocks the event loop and (b) the response carries a *measured*
``external_calls`` count instead of an assumed one.
"""
import asyncio
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class VisionAnalyzeRequest(BaseModel):
    file_path: str
    analysis_type: str = "general"   # general | pid | document | ocr | inspection
    prompt: Optional[str] = None


class VisionAnalyzeResponse(BaseModel):
    status: str
    result: dict
    model: str
    execution_time: float
    external_calls: int = 0
    equipment_tags: list = []


def _analyze_guarded(file_path: str, prompt: Optional[str], analysis_type: str) -> Dict[str, Any]:
    from agent.security.netguard import no_network
    from agent.tools.vision import analyze_image, extract_equipment_tags

    with no_network() as guard:
        result = analyze_image(file_path, prompt=prompt, analysis_type=analysis_type)
    return {
        "result": result,
        "equipment_tags": extract_equipment_tags(result),
        "external_calls": guard.external_calls,
    }


@router.post("/analyze", response_model=VisionAnalyzeResponse)
async def analyze(req: VisionAnalyzeRequest):
    from agent.tools.vision import VISION_MODEL_NAME
    from agent.config import VISION_ENDPOINT

    t0 = time.time()
    try:
        payload = await asyncio.to_thread(
            _analyze_guarded, req.file_path, req.prompt, req.analysis_type
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (PermissionError, ValueError, IsADirectoryError) as e:
        # Path denied / unsupported type — never leak internals.
        raise HTTPException(status_code=400, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        msg = str(e)
        # An unreachable local llama.cpp server surfaces as an OpenAI APIConnectionError.
        if "Connection" in type(e).__name__ or "connect" in msg.lower():
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Local vision model (Qwen2.5-VL) is not reachable on "
                    f"{VISION_ENDPOINT}. Start it with "
                    f"'python scripts/serve_model.py --model-id qwen-vision ... --port 8003'."
                ),
            )
        logger.error("vision analyze failed: %s", e)
        raise HTTPException(status_code=500, detail=f"vision analysis failed: {e}")

    result = payload["result"]
    return VisionAnalyzeResponse(
        status="completed",
        result=result,
        model=result.get("model", VISION_MODEL_NAME),
        execution_time=round(time.time() - t0, 3),
        external_calls=payload["external_calls"],
        equipment_tags=payload["equipment_tags"],
    )
