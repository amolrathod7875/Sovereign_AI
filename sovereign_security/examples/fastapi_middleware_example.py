"""Example of how to integrate the security subsystem via FastAPI middleware.

DO NOT import this file in the production backend. This is an example only.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from fastapi import Request
from fastapi.responses import JSONResponse
from sovereign_security.security_gateway import SecurityGateway
from sovereign_security.core.exceptions import SecurityError

async def security_middleware_example(request: Request, call_next):
    """
    Example middleware to validate incoming requests.
    """
    try:
        # Example: validate a file path if provided in headers/query
        file_path = request.query_params.get("file_path")
        if file_path:
            decision = SecurityGateway.validate_input(file_path=file_path)
            if not decision.allowed:
                return JSONResponse(status_code=403, content={"detail": f"Security Blocked: {decision.reason}"})
        
        # Process the request
        response = await call_next(request)
        
        # Note: Output validation would typically happen at the router level 
        # or via a custom Response class, as intercepting streaming responses 
        # in middleware is complex.
        
        return response
    except SecurityError as e:
        return JSONResponse(status_code=500, content={"detail": f"Internal Security Error: {str(e)}"})
    except Exception as e:
        # Fail-closed
        return JSONResponse(status_code=500, content={"detail": "Request aborted due to unexpected error"})
