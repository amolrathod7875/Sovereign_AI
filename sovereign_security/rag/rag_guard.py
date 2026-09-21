from .document_trust import DocumentTrustPolicy
from .retrieval_guard import RetrievalGuard
from .metadata_guard import MetadataGuard
from .poisoning_detector import PoisoningDetector
from ..core.exceptions import SecurityViolation

class RAGGuard:
    def __init__(self):
        self.trust_policy = DocumentTrustPolicy()
        self.retrieval_guard = RetrievalGuard()
        self.metadata_guard = MetadataGuard()
        self.poisoning_detector = PoisoningDetector()

    def validate_chunks(self, chunks: list):
        self.retrieval_guard.enforce(chunks)
        self.poisoning_detector.enforce(chunks)
        
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            self.metadata_guard.enforce(metadata)
            self.trust_policy.enforce(metadata)
