import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SandboxPolicy:
    """
    Policy enforcement for sandboxed code execution.
    """

    ALLOWED_MODULES = [
        "math",
        "statistics",
        "random",
        "datetime",
        "json",
        "re",
        "collections",
        "itertools",
        "functools",
        "operator",
        "string",
        "textwrap",
        "decimal",
        "fractions",
        "numpy",
        "pandas",
    ]

    BLOCKED_PATTERNS = [
        "import os",
        "import sys",
        "import subprocess",
        "import socket",
        "import requests",
        "import urllib",
        "import http",
        "import ftp",
        "from os",
        "from sys",
        "from subprocess",
        "from socket",
        "from requests",
        "eval(",
        "exec(",
        "open(",
        "file(",
        "__import__",
        "getattr",
        "setattr",
        "delattr",
        "compile(",
    ]

    def __init__(self):
        self.execution_count = 0
        self.blocked_count = 0

    def validate_code(self, code: str) -> tuple[bool, Optional[str]]:
        """
        Validate code against security policy.

        Returns:
            (is_valid, error_message)
        """
        code_lower = code.lower()

        for pattern in self.BLOCKED_PATTERNS:
            if pattern.lower() in code_lower:
                self.blocked_count += 1
                return False, f"Blocked pattern detected: {pattern}"

        self.execution_count += 1
        return True, None

    def get_stats(self) -> Dict[str, int]:
        """
        Get sandbox policy statistics.
        """
        return {
            "total_executions": self.execution_count,
            "blocked": self.blocked_count,
        }


sandbox_policy = SandboxPolicy()
