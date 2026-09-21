"""Input security and validation modules."""
from typing import Any
from ..core.decision import SecurityDecision
from .input_validator import InputValidator

def validate_input(file_path: str = None, mime_type: str = None) -> SecurityDecision:
    """Validate input files and paths."""
    validator = InputValidator()
    # Simplified entry point for the gateway
    if file_path:
        return validator.validate({"file_path": file_path, "mime_type": mime_type})
    return SecurityDecision.allow(domain="INPUT", reason="No input to validate")
