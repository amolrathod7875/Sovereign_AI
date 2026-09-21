from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class CapabilityPolicy(BasePolicy):
    def __init__(self, allowed_capabilities=None):
        self.allowed_capabilities = allowed_capabilities or []

    def evaluate(self, capability: str) -> SecurityDecision:
        if capability not in self.allowed_capabilities:
            return SecurityDecision.deny(f"Capability '{capability}' is DENIED", severity="HIGH", rule_id="AGT-CAP-001")
            
        return SecurityDecision.allow(f"Capability '{capability}' is ALLOWED", rule_id="AGT-CAP-000")

