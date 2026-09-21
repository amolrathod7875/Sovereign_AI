"""RAG security and validation modules."""
from typing import List, Dict, Any
from ..core.decision import SecurityDecision
from .rag_guard import RAGGuard

def validate_rag(documents: List[Dict[str, Any]]) -> SecurityDecision:
    """Validate retrieved RAG documents for poisoning and trust."""
    guard = RAGGuard()
    return guard.evaluate(documents)
