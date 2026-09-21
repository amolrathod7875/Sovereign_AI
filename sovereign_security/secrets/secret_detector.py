import re
from typing import List, Dict

class SecretDetector:
    PATTERNS = {
        "API_KEY": r"(?i)(api[_-]?key[\s:=]+['\"]?)([a-zA-Z0-9_\-]{20,})(['\"]?)",
        "PASSWORD": r"(?i)(password[\s:=]+['\"]?)([^'\"\s]{8,})(['\"]?)",
        "JWT": r"eyJ[a-zA-Z0-9_=]+(?:\.eyJ[a-zA-Z0-9_=]+)+(?:\.[a-zA-Z0-9_\-\+\/=]+)",
        "PRIVATE_KEY": r"-----BEGIN [A-Z]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z]+ PRIVATE KEY-----",
        "DB_CONN": r"(?i)(postgresql|postgres|mysql|mongodb)://[^:]+:[^@]+@[^/]+/[^\s]+"
    }

    def scan(self, text: str) -> List[Dict]:
        findings = []
        for secret_type, pattern in self.PATTERNS.items():
            for match in re.finditer(pattern, text):
                findings.append({
                    "type": secret_type,
                    "location": (match.start(), match.end())
                })
        return findings

    @classmethod
    def redact(cls, text: str) -> str:
        redacted_text = text
        for secret_type, pattern in cls.PATTERNS.items():
            def replace_match(m):
                if len(m.groups()) == 3: # Format where secret is in middle group
                    return m.group(1) + "REDACTED" + m.group(3)
                return "REDACTED"
            redacted_text = re.sub(pattern, replace_match, redacted_text)
        return redacted_text
