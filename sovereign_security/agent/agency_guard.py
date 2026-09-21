from .capability_policy import CapabilityPolicy
from .tool_policy import ToolPolicy
from .action_guard import ActionGuard
from ..core.exceptions import AuthorizationError

class AgencyGuard:
    def __init__(self, allowed_capabilities=None, allowed_tools=None):
        self.capability_policy = CapabilityPolicy(allowed_capabilities)
        self.tool_policy = ToolPolicy(allowed_tools)
        self.action_guard = ActionGuard()

    def enforce_tool(self, tool_name: str):
        decision = self.tool_policy.evaluate(tool_name)
        if not decision.allowed:
            raise AuthorizationError(f"Unauthorized Tool: {decision.reason}")

    def enforce_capability(self, capability: str):
        self.capability_policy.enforce(capability)

    def enforce_action(self, action: dict):
        self.action_guard.enforce(action)

    def evaluate(self, tool_name: str):
        from ..core.decision import SecurityDecision
        try:
            self.enforce_tool(tool_name)
            return SecurityDecision.allow(domain="AGENT", reason="Tool allowed")
        except Exception as e:
            return SecurityDecision.deny(domain="AGENT", reason=str(e))
