"""Token usage extraction shared by LLM providers."""


def read_usage(raw_message: object) -> tuple[int, int]:
    """Return (tokens_in, tokens_out) from a raw message's usage_metadata.

    Returns (0, 0) when the message carries no usage information.
    """
    usage = getattr(raw_message, "usage_metadata", None) or {}
    return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))


def estimate_tokens(prompt: str, response_text: str) -> tuple[int, int]:
    """Rough token estimate (~4 chars per token) when the provider reports no usage.

    Estimates are flagged via ``tokens_estimated`` in LLMLogger so queried
    costs can be distinguished from metered ones.
    """
    return max(1, len(prompt) // 4), max(1, len(response_text) // 4)
