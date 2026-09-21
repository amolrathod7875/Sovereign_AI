"""Prompt security and injection detection."""
from ..core.decision import SecurityDecision
from .prompt_guard import PromptGuard

def inspect_prompt(prompt_text: str) -> SecurityDecision:
    """Inspect a prompt for injection attempts."""
    guard = PromptGuard()
    return guard.evaluate(prompt_text)
