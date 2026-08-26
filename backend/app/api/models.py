from fastapi import APIRouter, HTTPException
from typing import List, Optional

from app.schemas import ModelInfo

router = APIRouter()


@router.get("")
async def list_models() -> List[ModelInfo]:
    from app.models.registry import model_registry

    models = []
    for model_id, model in model_registry.list_models():
        models.append(
            ModelInfo(
                id=model_id,
                name=model["name"],
                endpoint=model["endpoint"],
                capabilities=model["capabilities"],
                context_length=model.get("context_length", 8192),
                status=model["status"],
                vram_gb=model.get("vram_gb"),
            )
        )
    return models


@router.get("/{model_id}")
async def get_model(model_id: str) -> ModelInfo:
    from app.models.registry import model_registry

    model = model_registry.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return ModelInfo(
        id=model_id,
        name=model["name"],
        endpoint=model["endpoint"],
        capabilities=model["capabilities"],
        context_length=model.get("context_length", 8192),
        status=model["status"],
        vram_gb=model.get("vram_gb"),
    )


@router.post("/route")
async def route_model(task_type: str, has_image: bool = False) -> dict:
    from app.models.router import route_task

    model_id = route_task(task_type, has_image)
    return {"model_id": model_id, "task_type": task_type, "has_image": has_image}


@router.post("/load/{model_id}")
async def load_model(model_id: str):
    from app.models.client import model_loader

    try:
        await model_loader.load_model(model_id)
        return {"status": "loaded", "model_id": model_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/unload/{model_id}")
async def unload_model(model_id: str):
    from app.models.client import model_loader

    try:
        await model_loader.unload_model(model_id)
        return {"status": "unloaded", "model_id": model_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
