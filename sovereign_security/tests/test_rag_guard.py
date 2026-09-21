import pytest
from sovereign_security.rag.document_trust import DocumentTrustPolicy

def test_untrusted_document():
    policy = DocumentTrustPolicy()
    decision = policy.evaluate({"source": "user_upload", "trust_level": "untrusted"})
    # Review returns allowed=False pending human review
    assert not decision.allowed
    assert decision.decision == "REVIEW"
    
def test_missing_source():
    policy = DocumentTrustPolicy()
    decision = policy.evaluate({"trust_level": "trusted"})
    assert not decision.allowed
