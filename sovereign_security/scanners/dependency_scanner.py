import os

class DependencyScanner:
    def scan(self, req_file_path: str) -> list:
        findings = []
        if not os.path.exists(req_file_path):
            return findings
            
        with open(req_file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                # Extremely simple example: warn on missing version pins
                line = line.strip()
                if line and not line.startswith("#") and "==" not in line and ">=" not in line:
                    findings.append({
                        "file": req_file_path,
                        "line": line_no,
                        "issue": "Unpinned dependency",
                        "package": line
                    })
        return findings
