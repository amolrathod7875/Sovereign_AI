from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class PoisoningDetector(BasePolicy):
    def evaluate(self, chunks: list) -> SecurityDecision:
        # Simple detector looking for repetitive identical chunks or conflicting source identities
        sources = set()
        for chunk in chunks:
            source = chunk.get("metadata", {}).get("source")
            if source:
                sources.add(source)
                
        if len(sources) > 20: # arbitrary threshold for suspicious spread
            return SecurityDecision.review("Suspiciously high number of distinct sources in single retrieval", rule_id="RAG-POIS-001")
            
        return SecurityDecision.allow("No poisoning patterns detected", rule_id="RAG-POIS-000")

