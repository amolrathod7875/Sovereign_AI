import pytest
from sovereign_security.network.airgap_guard import AirgapGuard

def test_airgap_guard():
    guard = AirgapGuard()
    with guard.enforce():
        pass # If no exception is raised, the context manager works conceptually
