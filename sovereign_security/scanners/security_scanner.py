import json
from pathlib import Path
from .dependency_scanner import DependencyScanner
from .secret_scanner import SecretScanner

class SecurityScanner:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.reports_dir = self.repo_root / "security" / "reports"
        self.dependency_scanner = DependencyScanner()
        self.secret_scanner = SecretScanner()

    def run_full_scan(self):
        findings = {
            "dependencies": [],
            "secrets": []
        }
        
        # Scan dependencies
        req_path = self.repo_root / "backend" / "requirements.txt"
        findings["dependencies"] = self.dependency_scanner.scan(str(req_path))
        
        # Scan config for secrets (example)
        config_path = self.repo_root / "backend" / "app" / "config.py"
        findings["secrets"] = self.secret_scanner.scan_file(str(config_path))
        
        # Write findings
        findings_path = self.reports_dir / "SECURITY_FINDINGS.json"
        with open(findings_path, "w", encoding="utf-8") as f:
            json.dump(findings, f, indent=2)

if __name__ == "__main__":
    scanner = SecurityScanner(str(Path.cwd()))
    scanner.run_full_scan()
