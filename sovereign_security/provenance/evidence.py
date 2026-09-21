from dataclasses import dataclass
from typing import Optional

@dataclass
class Evidence:
    source_file: str
    source_type: str
    claim: str
    evidence: str
    entity: str
    confidence: float
    model: str
    timestamp: str
    origin: str
    security_status: str
    page: Optional[int] = None

    def is_verified(self) -> bool:
        return self.security_status == "verified" and self.confidence >= 0.8
