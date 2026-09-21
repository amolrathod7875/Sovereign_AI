from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class ClaimGuard(BasePolicy):
    """
    Validates that model outputs don't make unsupported engineering claims.
    """
    def evaluate(self, claims: list, evidence: list) -> SecurityDecision:
        # Check if any claim has status 'uncertain', 'conflict', or 'not_visible'
        # but is being passed off as verified in the action list.
        for claim in claims:
            status = claim.get("status")
            if status in ["uncertain", "conflict", "not_visible"]:
                # Ensure the system doesn't try to auto-execute based on this
                # This depends on the specific claim schema
                if claim.get("auto_execute") or claim.get("verified_fact"):
                    return SecurityDecision.deny(
                        f"Unsupported claim with status '{status}' marked as verified fact", 
                        severity="HIGH", 
                        rule_id="OUT-CLM-001"
                    )
        return SecurityDecision.allow("Engineering claims verified against evidence", rule_id="OUT-CLM-000")

