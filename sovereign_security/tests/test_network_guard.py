import pytest
from sovereign_security.network.network_policy import NetworkPolicy

def test_network_policy_localhost():
    policy = NetworkPolicy()
    assert policy.evaluate("http://localhost:8080/api").allowed
    assert policy.evaluate("http://127.0.0.1:8000/v1").allowed

def test_network_policy_external():
    policy = NetworkPolicy()
    assert not policy.evaluate("http://example.com/api").allowed
