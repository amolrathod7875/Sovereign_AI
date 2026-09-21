from datetime import datetime
import json
import logging
from ..core.decision import SecurityDecision
from ..secrets.redactor import Redactor

class AuditLogger:
    def __init__(self, log_file: str = "security/reports/audit.log"):
        self.log_file = log_file
        self.redactor = Redactor()
        
        self.logger = logging.getLogger("security_audit")
        self.logger.setLevel(logging.INFO)
        
        # In a real system we would configure a FileHandler here,
        # but for this standalone module, we'll implement a basic file append.

    def log_event(self, event_type: str, decision: SecurityDecision, details: dict):
        # Redact any secrets before logging
        safe_details = {k: self.redactor.redact(str(v)) for k, v in details.items()}
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            "decision": decision.decision,
            "rule_id": decision.rule_id,
            "reason": decision.reason,
            "details": safe_details
        }
        
        # Write to log file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            self.logger.error(f"Failed to write audit log: {e}")
