from abc import ABC, abstractmethod
from typing import Any
from .decision import SecurityDecision
from .exceptions import SecurityViolation

class BasePolicy(ABC):
    
    @abstractmethod
    def evaluate(self, context: Any) -> SecurityDecision:
        pass
        
    def enforce(self, input_data: Any) -> None:
        """Evaluate and raise an exception if denied."""
        decision = self.evaluate(input_data)
        if not decision.allowed:
            raise SecurityViolation(f"Security Policy Violated: {decision.reason} [Rule: {decision.rule_id}]")
