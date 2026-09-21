from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class HallucinationGuard(BasePolicy):
    def evaluate(self, output: str, sources: list) -> SecurityDecision:
        # Placeholder for deeper hallucination checking logic
        # e.g., NLI cross-checking against sources
        if not sources and len(output) > 500:
            return SecurityDecision.review("Large output generated with no sources, potential hallucination", rule_id="OUT-HAL-001")
        return SecurityDecision.allow("Output appears grounded", rule_id="OUT-HAL-000")

