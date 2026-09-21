from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class MetadataGuard(BasePolicy):
    def evaluate(self, metadata: dict) -> SecurityDecision:
        # Check for executable code embedded in metadata or massive payloads
        if str(metadata).find("eval(") != -1 or str(metadata).find("exec(") != -1:
            return SecurityDecision.deny("Executable payload found in metadata", severity="HIGH", rule_id="RAG-META-001")
            
        if len(str(metadata)) > 10000:
            return SecurityDecision.deny("Metadata payload is excessively large", severity="MEDIUM", rule_id="RAG-META-002")
            
        return SecurityDecision.allow("Metadata is safe", rule_id="RAG-META-000")

