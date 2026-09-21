from typing import Any, List, Dict, Tuple
from .core.decision import SecurityDecision
from .input import validate_input
from .prompt import inspect_prompt
from .output import validate_output
from .agent import authorize_tool
from .rag import validate_rag
from .network import validate_network
from .secrets import inspect_secret
from .audit import record_audit, EVENT_INPUT_ACCEPTED, EVENT_INPUT_DENIED, EVENT_PROMPT_ACCEPTED, EVENT_PROMPT_INJECTION_DETECTED, EVENT_OUTPUT_ACCEPTED, EVENT_OUTPUT_DENIED, EVENT_TOOL_AUTHORIZED, EVENT_TOOL_DENIED, EVENT_RAG_CONTENT_ACCEPTED, EVENT_RAG_CONTENT_DENIED, EVENT_NETWORK_ENDPOINT_ACCEPTED, EVENT_NETWORK_ENDPOINT_DENIED

class SecurityGateway:
    """Central entry point for all security subsystems.
    
    This class orchestrates security checks and ensures consistent audit logging.
    Future applications should instantiate and call this gateway rather than
    calling individual security modules directly.
    """

    @staticmethod
    def validate_input(file_path: str = None, mime_type: str = None) -> SecurityDecision:
        decision = validate_input(file_path, mime_type)
        event = EVENT_INPUT_ACCEPTED if decision.allowed else EVENT_INPUT_DENIED
        record_audit(event, decision, {"file_path": file_path, "mime_type": mime_type})
        return decision

    @staticmethod
    def inspect_prompt(prompt_text: str) -> SecurityDecision:
        decision = inspect_prompt(prompt_text)
        event = EVENT_PROMPT_ACCEPTED if decision.allowed else EVENT_PROMPT_INJECTION_DETECTED
        record_audit(event, decision, {"prompt_length": len(prompt_text)})
        return decision

    @staticmethod
    def validate_output(output_data: Any, expected_schema: dict = None, evidence_list: list = None) -> SecurityDecision:
        decision = validate_output(output_data, expected_schema, evidence_list)
        event = EVENT_OUTPUT_ACCEPTED if decision.allowed else EVENT_OUTPUT_DENIED
        record_audit(event, decision, {"has_schema": bool(expected_schema)})
        return decision

    @staticmethod
    def authorize_tool(tool_name: str, allowed_tools: list = None) -> SecurityDecision:
        decision = authorize_tool(tool_name, allowed_tools)
        event = EVENT_TOOL_AUTHORIZED if decision.allowed else EVENT_TOOL_DENIED
        record_audit(event, decision, {"tool_name": tool_name})
        return decision

    @staticmethod
    def validate_rag(documents: List[Dict[str, Any]]) -> SecurityDecision:
        decision = validate_rag(documents)
        event = EVENT_RAG_CONTENT_ACCEPTED if decision.allowed else EVENT_RAG_CONTENT_DENIED
        record_audit(event, decision, {"document_count": len(documents)})
        return decision

    @staticmethod
    def validate_network(endpoint_url: str) -> SecurityDecision:
        decision = validate_network(endpoint_url)
        event = EVENT_NETWORK_ENDPOINT_ACCEPTED if decision.allowed else EVENT_NETWORK_ENDPOINT_DENIED
        record_audit(event, decision, {"endpoint_url": endpoint_url})
        return decision

    @staticmethod
    def inspect_secret(text: str) -> Tuple[bool, str, list]:
        # Secrets don't return a standard decision but rather (has_secrets, redacted, findings)
        has_secrets, redacted, findings = inspect_secret(text)
        if has_secrets:
            # We construct a synthetic decision for audit logging
            decision = SecurityDecision.deny(reason="Secrets detected", domain="SECRETS")
            record_audit("SECRET_DETECTED", decision, {"finding_count": len(findings)})
        return has_secrets, redacted, findings

    @staticmethod
    def record_audit(event_type: str, decision: SecurityDecision, details: dict = None):
        """Direct access to the audit log if needed."""
        record_audit(event_type, decision, details)
