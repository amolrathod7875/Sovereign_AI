"""Output validation and guardrails."""
from typing import Any
from ..core.decision import SecurityDecision
from .output_guard import OutputGuard

def validate_output(output_data: Any, expected_schema: dict = None, evidence_list: list = None) -> SecurityDecision:
    """Validate LLM/VLM outputs against schemas and claims."""
    guard = OutputGuard()
    return guard.evaluate(output_data, expected_schema, evidence_list)
