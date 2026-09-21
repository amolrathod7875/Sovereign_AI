import os
from pathlib import Path
from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class PathGuard(BasePolicy):
    def __init__(self, allowed_roots=None):
        self.allowed_roots = allowed_roots or []

    def evaluate(self, file_path: str) -> SecurityDecision:
        try:
            # Resolve to absolute path, neutralizing symlinks and ../
            resolved_path = Path(file_path).resolve(strict=False)
            path_str = str(resolved_path)
            
            # Check for path traversal attempts like containing ..
            if ".." in str(file_path):
                return SecurityDecision.deny("Path traversal detected (..) in input path", severity="HIGH", rule_id="INP-PATH-001")

            # Check if path is within allowed boundaries
            if self.allowed_roots:
                allowed = False
                for root in self.allowed_roots:
                    root_path = str(Path(root).resolve())
                    if path_str.startswith(root_path + os.sep) or path_str == root_path:
                        allowed = True
                        break
                
                if not allowed:
                    return SecurityDecision.deny(f"Path outside allowed directories: {path_str}", severity="HIGH", rule_id="INP-PATH-002")

            return SecurityDecision.allow("Path resolved safely", rule_id="INP-PATH-000")
        except Exception as e:
            return SecurityDecision.deny(f"Path resolution error: {str(e)}", severity="HIGH", rule_id="INP-PATH-003")

