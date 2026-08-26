from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class SandboxExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    timeout_seconds: Optional[int] = None


class SandboxExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int


@router.post("/execute")
async def execute_code(request: SandboxExecuteRequest):
    from app.tools.python_tool import execute_in_sandbox

    try:
        result = await execute_in_sandbox(
            code=request.code,
            language=request.language,
            timeout=request.timeout_seconds,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def sandbox_status():
    from app.tools.python_tool import get_sandbox_status

    return await get_sandbox_status()
