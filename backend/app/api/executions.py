from fastapi import APIRouter, HTTPException
from typing import Optional, List

from app.schemas import ExecutionResponse

router = APIRouter()


@router.get("/{execution_id}")
async def get_execution(execution_id: str) -> ExecutionResponse:
    from app.storage.postgres import get_execution_by_id

    execution = await get_execution_by_id(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.get("")
async def list_executions(
    limit: int = 50,
    offset: int = 0,
    task_type: Optional[str] = None,
) -> List[ExecutionResponse]:
    from app.storage.postgres import list_executions

    executions = await list_executions(limit=limit, offset=offset, task_type=task_type)
    return executions
