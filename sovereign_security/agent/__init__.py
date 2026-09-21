"""Agent security and validation modules."""
from ..core.decision import SecurityDecision
from .agency_guard import AgencyGuard

def authorize_tool(tool_name: str, allowed_tools: list = None) -> SecurityDecision:
    """Authorize a tool execution based on agent capability policy."""
    guard = AgencyGuard(allowed_tools=allowed_tools)
    return guard.evaluate(tool_name)
