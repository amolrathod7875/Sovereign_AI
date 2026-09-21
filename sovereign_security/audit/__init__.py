"""Audit logging modules."""
from .audit_logger import AuditLogger
from .events import *

def record_audit(event_type: str, decision: "SecurityDecision", details: dict = None):
    """Record a security audit event."""
    logger = AuditLogger()
    logger.log_event(event_type, decision, details or {})
