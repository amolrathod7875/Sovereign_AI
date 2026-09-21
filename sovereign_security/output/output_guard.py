from .schema_guard import SchemaGuard
from .claim_guard import ClaimGuard
from .secret_guard import SecretGuard
from .hallucination_guard import HallucinationGuard
from ..core.exceptions import SecurityViolation

class OutputGuard:
    def __init__(self):
        self.schema_guard = SchemaGuard()
        self.claim_guard = ClaimGuard()
        self.secret_guard = SecretGuard()
        self.hallucination_guard = HallucinationGuard()

    def validate_json_output(self, content: str):
        self.schema_guard.enforce(content)
        self.secret_guard.enforce(content)

    def validate_claims(self, claims: list, evidence: list):
        self.claim_guard.enforce(claims, evidence)
