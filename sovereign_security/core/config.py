"""Centralized configuration for the standalone security subsystem.
This module is isolated from the application configuration to ensure
fail-safe behavior and prevent dependency on external environment variables.
"""

from dataclasses import dataclass, field
from typing import List

@dataclass
class SecurityConfig:
    # Network Security defaults
    allowed_hosts: List[str] = field(default_factory=lambda: ["localhost", "127.0.0.1", "::1"])
    approved_endpoints: List[str] = field(default_factory=lambda: [])
    
    # Path Security defaults
    allowed_roots: List[str] = field(default_factory=lambda: [])
    
    # File Security defaults
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10 MB limit
    
    # Audit defaults
    audit_log_path: str = "security/reports/audit.log"
    
    # Agent Capability defaults
    default_allowed_capabilities: List[str] = field(default_factory=lambda: [])

    # Provenance requirements
    require_strict_provenance: bool = True
    minimum_confidence_threshold: float = 0.8

# Global, immutable config instance for the subsystem.
# If future integration requires dynamic updates, it must provide a secure setter.
config = SecurityConfig()
