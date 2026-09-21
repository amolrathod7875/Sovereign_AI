import pytest
from sovereign_security.input.path_guard import PathGuard
import os

def test_path_traversal():
    guard = PathGuard(allowed_roots=[os.getcwd()])
    
    # Absolute paths traversal
    decision = guard.evaluate("../../../etc/passwd")
    assert decision.allowed == False
    assert decision.decision == "DENY"
    assert "traversal" in decision.reason.lower() or "outside" in decision.reason.lower()

    # Allowed path
    decision = guard.evaluate(os.path.join(os.getcwd(), "safe.txt"))
    assert decision.allowed == True
