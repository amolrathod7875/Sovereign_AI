from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision
from ..prompt.injection_detector import InjectionDetector

class RetrievalGuard(BasePolicy):
    def evaluate(self, chunks: list) -> SecurityDecision:
        detector = InjectionDetector()
        
        for chunk in chunks:
            text = chunk.get("text", "")
            # Check for injection embedded in the text
            if not detector.evaluate(text).allowed:
                return SecurityDecision.deny("Prompt injection detected in retrieved chunk", severity="HIGH", rule_id="RAG-RET-001")
                
        return SecurityDecision.allow("Retrieved chunks are safe", rule_id="RAG-RET-000")

