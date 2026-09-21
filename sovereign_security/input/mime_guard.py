import mimetypes
from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision
from ..core.constants import ALLOWED_MIME_TYPES

class MimeGuard(BasePolicy):
    def evaluate(self, file_path: str) -> SecurityDecision:
        mime_type, _ = mimetypes.guess_type(file_path)
        
        if mime_type is None:
            return SecurityDecision.review("MIME type could not be determined", rule_id="INP-MIME-001")
            
        if mime_type not in ALLOWED_MIME_TYPES:
            return SecurityDecision.deny(f"Disallowed MIME type: {mime_type}", severity="MEDIUM", rule_id="INP-MIME-002")
            
        return SecurityDecision.allow("MIME type allowed", rule_id="INP-MIME-000")

