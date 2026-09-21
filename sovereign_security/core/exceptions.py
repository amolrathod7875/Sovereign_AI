class SecurityError(Exception):
    """Base exception for all security violations and internal security failures."""
    pass

class InputSecurityError(SecurityError):
    """Raised when an input violates security policy (e.g., path traversal, invalid file)."""
    pass

class PromptInjectionError(SecurityError):
    """Raised when a prompt injection attempt is detected."""
    pass

class OutputSecurityError(SecurityError):
    """Raised when the generated output violates schema or hallucination policies."""
    pass

class AuthorizationError(SecurityError):
    """Raised when a tool, capability, or action is denied by policy."""
    pass

class NetworkSecurityError(SecurityError):
    """Raised when a network violation or airgap breach is detected."""
    pass

class SecretSecurityError(SecurityError):
    """Raised when a secret leak is detected and cannot be redacted."""
    pass

class SecurityViolation(SecurityError):
    """Generic policy violation error."""
    pass
