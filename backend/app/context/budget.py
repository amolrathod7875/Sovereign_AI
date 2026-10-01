CONVERSATION_CONTEXT_MAX_MESSAGES = 20
CONVERSATION_CONTEXT_TOKEN_BUDGET = 500


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
