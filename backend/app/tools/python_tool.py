import httpx
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from app.config import settings
from app.models.registry import is_local_endpoint
from agent.security.netguard import no_network

logger = logging.getLogger(__name__)


def is_internal_piston_url(url: str) -> bool:
    """True iff ``url`` points to an INTERNAL/LOCAL Piston sandbox.

    Reuses the model-registry local-endpoint guard (loopback / RFC1918 private
    IPs) and additionally permits internal docker/service hostnames (single-label
    names such as ``piston`` or ``postgres``) which only resolve inside the
    private deployment network. Public FQDNs (``example.com``, ``api.openai.com``)
    are rejected so code execution can never be offloaded to an external service.
    """
    if not url:
        return False
    if is_local_endpoint(url):
        return True
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if "." not in host:
        # Internal service name (docker-compose / k8s service without a domain).
        return True
    if host.endswith((".local", ".internal", ".svc", ".docker.internal")):
        return True
    return False


def validate_piston_url(url: str) -> None:
    """Raise ``ConnectionError`` if ``url`` is not an internal/local Piston host."""
    if not is_internal_piston_url(url):
        raise ConnectionError(
            f"Piston endpoint '{url}' is not internal/local. "
            f"Code execution must remain on the sovereign network "
            f"(no external/cloud offload)."
        )


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

    # Sovereignty: Piston must be an internal/local endpoint. A tampered
    # PISTON_URL pointing at an external host is rejected before any request.
    validate_piston_url(settings.PISTON_URL)

    try:
        # Defense in depth: even an allowed internal Piston URL is executed under
        # the network guard so no unexpected external socket can be opened.
        with no_network():
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
    # Sovereignty: never probe an external Piston endpoint.
    validate_piston_url(settings.PISTON_URL)
    try:
        with no_network():
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{settings.PISTON_URL}/status")
                if response.status_code == 200:
                    return {"status": "online", "details": response.json()}
                return {"status": "error", "details": response.text}
    except Exception as e:
        return {"status": "offline", "error": str(e)}
