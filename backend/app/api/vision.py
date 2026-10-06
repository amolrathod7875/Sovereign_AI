from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.conversations.service import persist_assistant_message
from app.storage.postgres import async_session
from app.identity.principal import Principal, get_current_principal_dep

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
router = APIRouter()


class VisionAnalyzeRequest(BaseModel):
    file_path: str
    analysis_type: str = "general"   # general | pid | document | ocr | inspection
    prompt: Optional[str] = None
    conversation_id: Optional[str] = None


class VisionAnalyzeResponse(BaseModel):
    status: str
    result: dict
    model: str
    execution_time: float
    external_calls: int = 0
    equipment_tags: list = []
    response_time_seconds: Optional[float] = None
    model_performance: Optional[Dict[str, Any]] = None
    assistant_message_id: Optional[str] = None


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
async def analyze(req: VisionAnalyzeRequest, principal: Principal = Depends(get_current_principal_dep)):
    from agent.tools.vision import VISION_MODEL_NAME, VisionUpstreamResponseError, VisionModelBusyError
    from agent.config import VISION_ENDPOINT

    request_started = time.perf_counter()
    t0 = time.time()
    run_id = f"vision_{uuid.uuid4().hex[:12]}"
    try:
        payload = await asyncio.to_thread(
            _analyze_guarded, req.file_path, req.prompt, req.analysis_type
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (PermissionError, ValueError, IsADirectoryError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(
            status_code=504,
            detail=(
                f"Local vision model (Qwen2.5-VL) analysis timed out on "
                f"{VISION_ENDPOINT}. The model may be overloaded or the image large. "
                f"Try a simpler task or check the model server."
            ),
        )
    except OSError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Local vision model (Qwen2.5-VL) is not reachable on "
                f"{VISION_ENDPOINT}. Start it with "
                f"'python scripts/serve_model.py --model-id qwen-vision ... --port 8003'. "
                f"Transport error: {e}"
            ),
        )
    except VisionModelBusyError as e:
        raise HTTPException(
            status_code=429,
            detail=(
                "Local GPU inference capacity is busy. Try again shortly."
            ),
            headers={"Retry-After": "5"},
        )
    except VisionUpstreamResponseError as e:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Local vision model (Qwen2.5-VL) returned an invalid response from "
                f"{VISION_ENDPOINT}. The model may be corrupted or misbehaving."
            ),
        )
    except Exception as e:
        msg = str(e)
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
    response_time_seconds = round(time.perf_counter() - request_started, 3)
    response = VisionAnalyzeResponse(
        status="completed",
        result=result,
        model=result.get("model", VISION_MODEL_NAME),
        execution_time=round(time.time() - t0, 3),
        external_calls=payload["external_calls"],
        equipment_tags=payload["equipment_tags"],
        response_time_seconds=response_time_seconds,
        model_performance=None,
    )

    assistant_message_id: Optional[str] = None
    if req.conversation_id:
        try:
            async with async_session() as session:
                assistant = await persist_assistant_message(
                    session,
                    conversation_id=req.conversation_id,
                    organization_id=principal.organization_id,
                    principal=principal,
                    content=result.get("description") or "Vision analysis complete.",
                    status="COMPLETED",
                    mode="vision",
                    task_type=req.analysis_type,
                    actual_model=result.get("model", VISION_MODEL_NAME),
                    rag_used=False,
                    external_calls=payload["external_calls"],
                    response_time_seconds=response_time_seconds,
                    display_payload={
                        "result": result,
                        "equipment_tags": payload["equipment_tags"],
                    },
                    idempotency_key=run_id,
                )
                assistant_message_id = assistant.id
        except Exception:
            logger.warning("vision assistant persistence failed", exc_info=True)

    out = response.model_dump()
    if assistant_message_id:
        out["assistant_message_id"] = assistant_message_id
    return out
