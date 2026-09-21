import os
from ..secrets.secret_detector import SecretDetector

class SecretScanner:
    def __init__(self):
        self.detector = SecretDetector()

    def scan_file(self, file_path: str) -> list:
        findings = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                file_findings = self.detector.scan(content)
                for finding in file_findings:
                    finding["file"] = file_path
                    findings.append(finding)
        except Exception:
            pass # Ignore binary files or unreadable files for basic scanner
        return findings
