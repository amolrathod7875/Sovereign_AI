from .injection_detector import InjectionDetector
from .instruction_boundary import InstructionBoundaryGuard
from ..core.exceptions import PromptInjectionError

class PromptGuard:
    def __init__(self):
        self.injection_detector = InjectionDetector()
        self.boundary_guard = InstructionBoundaryGuard()

    def enforce_untrusted_content(self, content: str):
        """Scans untrusted content like uploaded files, OCR text, RAG chunks."""
        decision = self.injection_detector.evaluate(content)
        if not decision.allowed:
            raise PromptInjectionError(f"Prompt Injection Detected: {decision.reason}")

    def enforce_constructed_prompt(self, final_prompt: str):
        """Validates the final prompt before sending to LLM."""
        decision = self.boundary_guard.evaluate(final_prompt)
        if not decision.allowed:
            raise PromptInjectionError(f"Prompt Boundary Violation: {decision.reason}")

    def evaluate(self, prompt_text: str):
        from ..core.decision import SecurityDecision
        try:
            self.enforce_untrusted_content(prompt_text)
            return SecurityDecision.allow(domain="PROMPT", reason="Prompt clean")
        except Exception as e:
            return SecurityDecision.deny(domain="PROMPT", reason=str(e))
