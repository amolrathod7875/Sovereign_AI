"""Secret detection and redaction."""
from typing import Tuple
from .redactor import Redactor
from .secret_detector import SecretDetector

def inspect_secret(text: str) -> Tuple[bool, str, list]:
    """Inspect text for secrets, returning (has_secrets, redacted_text, findings)."""
    detector = SecretDetector()
    findings = detector.scan(text)
    redacted = detector.redact(text)
    return len(findings) > 0, redacted, findings
