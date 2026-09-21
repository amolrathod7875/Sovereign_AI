from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class InstructionBoundaryGuard(BasePolicy):
    """
    Enforces that untrusted data is encapsulated within clear boundaries
    so that it is not interpreted as instructions.
    """
    def evaluate(self, prompt: str) -> SecurityDecision:
        # Example check: ensure untrusted data tags exist if required
        # For simplicity, if we pass constructed prompt, we check if it has XML-like boundaries.
        if "<untrusted_data>" in prompt and "</untrusted_data>" not in prompt:
            return SecurityDecision.deny("Unclosed untrusted data boundary", severity="HIGH", rule_id="PRM-BND-001")
            
        return SecurityDecision.allow("Instruction boundaries are intact", rule_id="PRM-BND-000")

