from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision
import socket

class NetworkPolicy(BasePolicy):
    def __init__(self, allowed_hosts=None):
        self.allowed_hosts = allowed_hosts or ["localhost", "127.0.0.1", "::1"]

    def evaluate(self, endpoint: str) -> SecurityDecision:
        try:
            # Extract hostname from endpoint if it's a URL
            if "://" in endpoint:
                hostname = endpoint.split("://")[1].split("/")[0].split(":")[0]
            else:
                hostname = endpoint.split(":")[0]

            if hostname not in self.allowed_hosts:
                # Optionally resolve and check if it's a local IP
                ip = socket.gethostbyname(hostname)
                if ip not in ["127.0.0.1", "::1"] and not ip.startswith("10.") and not ip.startswith("192.168.") and not (ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31):
                    return SecurityDecision.deny(f"Network access denied to non-local host: {hostname} ({ip})", severity="HIGH", rule_id="NET-POL-001")
            
            return SecurityDecision.allow(f"Network access allowed for local host {hostname}", rule_id="NET-POL-000")
        except Exception as e:
            return SecurityDecision.deny(f"Error validating endpoint: {str(e)}", severity="HIGH", rule_id="NET-POL-002")

