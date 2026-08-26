import httpx
import logging
from typing import Dict, Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


async def execute_in_sandbox(
    code: str,
    language: str = "python",
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Execute code in the Piston sandbox.

    Args:
        code: Source code to execute
        language: Programming language (python, javascript, etc.)
        timeout: Execution timeout in seconds

    Returns:
        Execution result with stdout, stderr, exit_code, execution_time_ms
    """
    if timeout is None:
        timeout = settings.SANDBOX_TIMEOUT_SECONDS

    try:
        async with httpx.AsyncClient(timeout=timeout + 5) as client:
            response = await client.post(
                f"{settings.PISTON_URL}/execute",
                json={
                    "language": language,
                    "version": "*",
                    "files": [
                        {
                            "name": f"main.{'py' if language == 'python' else language}",
                            "content": code,
                        }
                    ],
                    "run_timeout": timeout * 1000,
                    "compile_timeout": timeout * 1000,
                    "compile_memory_limit": 256 * 1024 * 1024,
                    "run_memory_limit": 256 * 1024 * 1024,
                },
            )

            if response.status_code == 200:
                result = response.json()
                return {
                    "stdout": result.get("run", {}).get("stdout", ""),
                    "stderr": result.get("run", {}).get("stderr", ""),
                    "exit_code": result.get("run", {}).get("exit_code", 0),
                    "execution_time_ms": result.get("run", {}).get("execution_time", 0),
                }
            else:
                logger.error(f"Piston error: {response.status_code} - {response.text}")
                return {
                    "stdout": "",
                    "stderr": f"Sandbox error: {response.status_code}",
                    "exit_code": -1,
                    "execution_time_ms": 0,
                }

    except httpx.TimeoutException:
        logger.error(f"Piston timeout after {timeout}s")
        return {
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds",
            "exit_code": -1,
            "execution_time_ms": timeout * 1000,
        }
    except Exception as e:
        logger.error(f"Sandbox execution error: {e}")
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "execution_time_ms": 0,
        }


async def get_sandbox_status() -> Dict[str, Any]:
    """
    Get sandbox service status.
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings.PISTON_URL}/status")
            if response.status_code == 200:
                return {"status": "online", "details": response.json()}
            return {"status": "error", "details": response.text}
    except Exception as e:
        return {"status": "offline", "error": str(e)}
