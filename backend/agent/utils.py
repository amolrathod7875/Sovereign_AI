"""Small shared helpers (no external dependencies)."""
from datetime import datetime
from typing import Dict, Any, Optional


def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def trace_entry(node: str, action: str, tool: Optional[str], duration_ms: int,
                status: str, **extra: Any) -> Dict[str, Any]:
    """Build a single observability log entry.

    Logs every agent step with: timestamp, node, action, tool, duration, status.
    Sensitive raw document content is NOT logged here (only metadata).
    """
    entry = {
        "timestamp": now_iso(),
        "node": node,
        "action": action,
        "tool": tool,
        "duration_ms": duration_ms,
        "status": status,
    }
    for k, v in extra.items():
        if k not in entry:
            entry[k] = v
    return entry


def elapsed_ms(start: float) -> int:
    import time
    return int((time.time() - start) * 1000)
