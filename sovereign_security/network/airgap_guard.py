from .network_policy import NetworkPolicy
from .endpoint_guard import EndpointGuard
from ..core.exceptions import NetworkSecurityError
import contextlib

class AirgapGuard:
    def __init__(self, allowed_hosts=None, approved_endpoints=None):
        self.network_policy = NetworkPolicy(allowed_hosts)
        self.endpoint_guard = EndpointGuard(approved_endpoints)

    def validate_request(self, url: str):
        self.network_policy.enforce(url)
        if self.endpoint_guard.approved_endpoints:
            self.endpoint_guard.enforce(url)

    @contextlib.contextmanager
    def enforce(self):
        """Context manager to scope airgap operations conceptually."""
        # Conceptually enforces no external requests.
        # Currently a placeholder to demonstrate integration point.
        yield self
