import re
from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class InjectionDetector(BasePolicy):
    SUSPICIOUS_PATTERNS = [
        r"(?i)ignore previous instructions",
        r"(?i)ignore system instructions",
        r"(?i)reveal system prompt",
        r"(?i)show hidden instructions",
        r"(?i)disable security",
        r"(?i)bypass security",
        r"(?i)execute this command",
        r"(?i)call this tool",
        r"(?i)read this file",
        r"(?i)send this data",
        r"(?i)reveal credentials",
        r"(?i)new instructions:",
        r"(?i)system:"
    ]

    def evaluate(self, content: str) -> SecurityDecision:
        for pattern in self.SUSPICIOUS_PATTERNS:
            if re.search(pattern, content):
                return SecurityDecision.deny(f"Suspicious prompt injection pattern detected", severity="HIGH", rule_id="PRM-INJ-001")
        return SecurityDecision.allow("No obvious injection patterns detected", rule_id="PRM-INJ-000")

    @classmethod
    def detect(cls, content: str) -> SecurityDecision:
        return cls().evaluate(content)

