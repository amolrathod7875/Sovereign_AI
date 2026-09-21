import pytest
from sovereign_security.agent.capability_policy import CapabilityPolicy

def test_capability_policy():
    policy = CapabilityPolicy(["READ_FILE"])
    assert policy.evaluate("READ_FILE").allowed
    assert not policy.evaluate("NETWORK").allowed
