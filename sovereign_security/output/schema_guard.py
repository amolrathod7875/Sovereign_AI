import json
from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class SchemaGuard(BasePolicy):
    def evaluate(self, content: str) -> SecurityDecision:
        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                return SecurityDecision.deny("Output is not a valid JSON dictionary", severity="MEDIUM", rule_id="OUT-SCH-001")
            return SecurityDecision.allow("Output matches valid JSON format", rule_id="OUT-SCH-000")
        except json.JSONDecodeError:
            return SecurityDecision.deny("Malformed JSON output", severity="HIGH", rule_id="OUT-SCH-002")

