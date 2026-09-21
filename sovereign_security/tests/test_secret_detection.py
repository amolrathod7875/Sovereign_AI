import pytest
from sovereign_security.secrets.secret_detector import SecretDetector

def test_secret_redaction():
    detector = SecretDetector()
    text_with_secret = "Here is my db conn: postgresql://admin:password123@localhost:5432/db"
    
    findings = detector.scan(text_with_secret)
    assert len(findings) > 0
    
    redacted = detector.redact(text_with_secret)
    assert "password123" not in redacted
    assert "REDACTED" in redacted
