from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision
from ..secrets.secret_detector import SecretDetector

class SecretGuard(BasePolicy):
    def evaluate(self, output: str) -> SecurityDecision:
        detector = SecretDetector()
        findings = detector.scan(output)
        if findings:
            return SecurityDecision.deny("Output contains sensitive secrets", severity="HIGH", rule_id="OUT-SEC-001")
        return SecurityDecision.allow("No secrets in output", rule_id="OUT-SEC-000")

