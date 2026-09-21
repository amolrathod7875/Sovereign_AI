from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class ActionGuard(BasePolicy):
    def evaluate(self, action: dict) -> SecurityDecision:
        action_type = action.get("type")
        
        if action_type in ["SHELL", "EXECUTE_PROCESS"]:
            return SecurityDecision.deny(f"Direct {action_type} actions are strictly forbidden", severity="HIGH", rule_id="AGT-ACT-001")
            
        return SecurityDecision.allow(f"Action '{action_type}' permitted", rule_id="AGT-ACT-000")

