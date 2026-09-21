from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class EndpointGuard(BasePolicy):
    def __init__(self, approved_endpoints=None):
        self.approved_endpoints = approved_endpoints or []

    def evaluate(self, endpoint_url: str) -> SecurityDecision:
        if not self.approved_endpoints:
            return SecurityDecision.review("No explicit approved endpoints configured", rule_id="NET-END-001")
            
        if not any(endpoint_url.startswith(approved) for approved in self.approved_endpoints):
            return SecurityDecision.deny(f"Endpoint not in approved list: {endpoint_url}", severity="HIGH", rule_id="NET-END-002")
            
        return SecurityDecision.allow("Endpoint is explicitly approved", rule_id="NET-END-000")

