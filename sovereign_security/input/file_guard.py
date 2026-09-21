import os
from pathlib import Path
from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision
from ..core.constants import MAX_FILE_SIZE_BYTES, ALLOWED_EXTENSIONS

class FileGuard(BasePolicy):
    def evaluate(self, file_path: str) -> SecurityDecision:
        if not os.path.exists(file_path):
            return SecurityDecision.deny(f"File not found: {file_path}", severity="LOW", rule_id="INP-FILE-001")
        
        # Check size
        size = os.path.getsize(file_path)
        if size > MAX_FILE_SIZE_BYTES:
            return SecurityDecision.deny(f"File exceeds maximum allowed size ({size} bytes)", severity="MEDIUM", rule_id="INP-FILE-002")
        
        # Check extension
        ext = Path(file_path).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return SecurityDecision.deny(f"Disallowed file extension: {ext}", severity="MEDIUM", rule_id="INP-FILE-003")
            
        return SecurityDecision.allow("File constraints satisfied", rule_id="INP-FILE-000")

