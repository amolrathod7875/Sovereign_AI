from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class DocumentTrustPolicy(BasePolicy):
    def evaluate(self, doc_metadata: dict) -> SecurityDecision:
        # Require documents to have a known source and author
        source = doc_metadata.get("source")
        if not source:
            return SecurityDecision.deny("Document missing source metadata", severity="MEDIUM", rule_id="RAG-TRU-001")
            
        trust_level = doc_metadata.get("trust_level", "untrusted")
        if trust_level == "untrusted":
            return SecurityDecision.review("Retrieving untrusted document", rule_id="RAG-TRU-002")
            
        return SecurityDecision.allow("Document trust validated", rule_id="RAG-TRU-000")

