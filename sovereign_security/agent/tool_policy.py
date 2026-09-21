from ..core.policy import BasePolicy
from ..core.decision import SecurityDecision

class ToolPolicy(BasePolicy):
    def __init__(self, allowed_tools=None):
        self.allowed_tools = allowed_tools or []

    def evaluate(self, tool_name: str) -> SecurityDecision:
        if tool_name not in self.allowed_tools:
            return SecurityDecision.deny(f"Tool execution denied: {tool_name}", severity="HIGH", rule_id="AGT-TOOL-001")
        return SecurityDecision.allow(f"Tool {tool_name} allowed", rule_id="AGT-TOOL-000")

