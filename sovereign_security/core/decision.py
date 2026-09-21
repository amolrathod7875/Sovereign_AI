import json
from dataclasses import dataclass, asdict
from typing import Optional, Any, Dict

@dataclass
class SecurityDecision:
    allowed: bool
    decision: str  # ALLOW, DENY, REVIEW, QUARANTINE, ERROR
    reason: str
    rule_id: str
    severity: str  # INFO, LOW, MEDIUM, HIGH, CRITICAL
    security_domain: str
    metadata: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def allow(cls, reason: str = "Passed security checks", rule_id: str = "SEC-000", domain: str = "GENERAL", metadata: dict = None) -> "SecurityDecision":
        return cls(
            allowed=True,
            decision="ALLOW",
            reason=reason,
            rule_id=rule_id,
            severity="INFO",
            security_domain=domain,
            metadata=metadata or {}
        )

    @classmethod
    def deny(cls, reason: str, rule_id: str = "SEC-001", domain: str = "GENERAL", severity: str = "HIGH", metadata: dict = None) -> "SecurityDecision":
        return cls(
            allowed=False,
            decision="DENY",
            reason=reason,
            rule_id=rule_id,
            severity=severity,
            security_domain=domain,
            metadata=metadata or {}
        )

    @classmethod
    def review(cls, reason: str, rule_id: str = "SEC-002", domain: str = "GENERAL", severity: str = "MEDIUM", metadata: dict = None) -> "SecurityDecision":
        return cls(
            allowed=False,
            decision="REVIEW",
            reason=reason,
            rule_id=rule_id,
            severity=severity,
            security_domain=domain,
            metadata=metadata or {}
        )

    @classmethod
    def error(cls, reason: str, rule_id: str = "SEC-ERR", domain: str = "GENERAL", metadata: dict = None) -> "SecurityDecision":
        return cls(
            allowed=False,
            decision="ERROR",
            reason=reason,
            rule_id=rule_id,
            severity="CRITICAL",
            security_domain=domain,
            metadata=metadata or {}
        )
