import logging
from typing import List, Dict, Any
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

_network_events: List[Dict[str, Any]] = []


class NetworkMonitor:
    """
    Monitor network connections to ensure sovereignty.
    All outbound connections should be logged and audited.
    """

    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.blocked_count = 0
        self.allowed_count = 0
        self.external_api_calls = 0

    def log_connection(
        self,
        destination: str,
        port: int,
        action: str,
        process: str = "unknown",
        execution_id: str = None,
    ):
        """
        Log a network connection attempt.
        """
        event = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "destination": destination,
            "port": port,
            "action": action,
            "process": process,
            "execution_id": execution_id,
        }

        self.events.append(event)
        _network_events.append(event)

        if len(_network_events) > 1000:
            _network_events.pop(0)

        if action == "BLOCKED":
            self.blocked_count += 1
            logger.warning(f"Blocked connection: {destination}:{port} by {process}")
        elif action == "LOCAL":
            self.allowed_count += 1

        if self._is_external_api(destination):
            self.external_api_calls += 1
            logger.error(f"External API call detected: {destination} - THIS SHOULD NOT HAPPEN")

        return event

    def _is_external_api(self, destination: str) -> bool:
        """
        Check if destination is an external AI API.
        """
        external_patterns = [
            "api.openai.com",
            "api.anthropic.com",
            "api.cohere.ai",
            "api.huggingface.co",
            "generativeai.googleapis.com",
            "aiplatform.googleapis.com",
        ]
        return any(pattern in destination.lower() for pattern in external_patterns)

    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent network events.
        """
        return self.events[-limit:]

    def get_stats(self) -> Dict[str, int]:
        """
        Get network statistics.
        """
        return {
            "total_events": len(self.events),
            "blocked": self.blocked_count,
            "allowed": self.allowed_count,
            "external_api_calls": self.external_api_calls,
        }

    def reset(self):
        """
        Reset the network monitor.
        """
        self.events.clear()
        self.blocked_count = 0
        self.allowed_count = 0
        self.external_api_calls = 0


network_monitor = NetworkMonitor()


def log_blocked_connection(destination: str, port: int, process: str = "unknown", execution_id: str = None):
    """
    Convenience function to log a blocked connection.
    """
    return network_monitor.log_connection(destination, port, "BLOCKED", process, execution_id)


def log_allowed_connection(destination: str, port: int, process: str = "unknown", execution_id: str = None):
    """
    Convenience function to log an allowed local connection.
    """
    return network_monitor.log_connection(destination, port, "LOCAL", process, execution_id)


def get_network_stats() -> Dict[str, int]:
    """
    Get current network statistics.
    """
    return network_monitor.get_stats()
