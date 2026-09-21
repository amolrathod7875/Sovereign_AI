import pytest
from sovereign_security.output.schema_guard import SchemaGuard
from sovereign_security.output.claim_guard import ClaimGuard

def test_schema_guard_invalid():
    guard = SchemaGuard()
    decision = guard.evaluate("invalid json {")
    assert not decision.allowed
    
def test_schema_guard_valid():
    guard = SchemaGuard()
    decision = guard.evaluate('{"status": "ok"}')
    assert decision.allowed

def test_claim_guard():
    guard = ClaimGuard()
    claims = [{"status": "uncertain", "verified_fact": True}]
    decision = guard.evaluate(claims, [])
    assert not decision.allowed
