from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision
from ..core.constants import MAX_PDF_PAGES, MAX_IMAGE_PIXELS

class ResourceLimitsGuard(BasePolicy):
    def evaluate(self, resource_context: dict) -> SecurityDecision:
        # Expected context structure: {"type": "image|pdf", "pages": 10, "pixels": 100000}
        rtype = resource_context.get("type")
        
        if rtype == "pdf":
            pages = resource_context.get("pages", 0)
            if pages > MAX_PDF_PAGES:
                return SecurityDecision.deny(f"PDF pages ({pages}) exceeds limit ({MAX_PDF_PAGES})", severity="MEDIUM", rule_id="INP-RES-001")
        elif rtype == "image":
            pixels = resource_context.get("pixels", 0)
            if pixels > MAX_IMAGE_PIXELS:
                return SecurityDecision.deny(f"Image pixels ({pixels}) exceeds limit ({MAX_IMAGE_PIXELS})", severity="MEDIUM", rule_id="INP-RES-002")
                
        return SecurityDecision.allow("Resource limits satisfied", rule_id="INP-RES-000")

