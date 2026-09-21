"""Network and airgap security modules."""
from ..core.decision import SecurityDecision
from .airgap_guard import AirgapGuard

def validate_network(endpoint_url: str) -> SecurityDecision:
    """Validate that a network request complies with the airgap policy."""
    guard = AirgapGuard()
    # Assuming validate_request returns a decision in future/updated versions
    # For now we wrap the validation
    try:
        guard.validate_request(endpoint_url)
        return SecurityDecision.allow(domain="NETWORK", reason="Endpoint allowed")
    except Exception as e:
        return SecurityDecision.deny(domain="NETWORK", reason=str(e))
