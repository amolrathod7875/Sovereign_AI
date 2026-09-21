from typing import List, Optional
from .evidence import Evidence
from ..core.exceptions import SecurityViolation

class ProvenanceTracker:
    def __init__(self):
        self.evidences: List[Evidence] = []

    def record_evidence(self, evidence: Evidence):
        self.evidences.append(evidence)

    def verify_claim(self, claim: str) -> bool:
        # Check if the claim has supporting verified evidence
        has_support = any(
            e.claim == claim and e.is_verified()
            for e in self.evidence_chain
        )
        if not has_support:
            raise SecurityViolation(f"Claim unsupported by verified evidence: {claim}")
        return True
