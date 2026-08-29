"""FastAPI integration for the local vision tool.

Reuses the SINGLE vision tool implemented in ``agent.tools.vision`` (the same one
the LangGraph agent uses), so there is one tool system, not a parallel one.

Exposes:
  POST /api/vision/analyze   -> analyze an approved local image/PDF with the local VLM
"""
import logging
import time
from typing import Optional

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


@router.post("/analyze", response_model=VisionAnalyzeResponse)
async def analyze(req: VisionAnalyzeRequest):
    from agent.tools.vision import analyze_image, VISION_MODEL_NAME

    t0 = time.time()
    try:
        result = analyze_image(req.file_path, prompt=req.prompt, analysis_type=req.analysis_type)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (PermissionError, ValueError, ConnectionError) as e:
        # Path denied / unsupported / non-local endpoint — never leak internals.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("vision analyze failed: %s", e)
        raise HTTPException(status_code=500, detail=f"vision analysis failed: {e}")

    return VisionAnalyzeResponse(
        status="completed",
        result=result,
        model=result.get("model", VISION_MODEL_NAME),
        execution_time=round(time.time() - t0, 3),
    )
