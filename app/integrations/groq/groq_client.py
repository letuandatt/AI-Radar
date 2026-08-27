"""Groq LLM client configuration using LangChain.

This file contains ALL Groq-specific parameters. To adjust model settings
(model name, temperature, max_tokens, etc.), modify this file only.
Do NOT dig into LangChain source code.

Provider: Groq (via langchain-groq)
Fallback Model: llama-3.3-70b-versatile
"""

from langchain_groq import ChatGroq
from pydantic import SecretStr

from app.core.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# GROQ MODEL PARAMETERS — Edit here to adjust behavior
# ============================================================================
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_TEMPERATURE = 0.1  # Low = deterministic extraction
GROQ_MAX_TOKENS = 1024  # summary + topics + entities + score


# ============================================================================


def create_groq_chat_model(api_key: SecretStr) -> ChatGroq:
    """Create a configured ChatGroq instance.

    Args:
        api_key: Groq API key (from settings/env).

    Returns:
        Configured ChatGroq instance ready for use.
    """
    logger.info(
        "Creating Groq chat model: %s (temp=%.1f, max_tokens=%d)",
        GROQ_MODEL,
        GROQ_TEMPERATURE,
        GROQ_MAX_TOKENS,
    )

    return ChatGroq(
        model=GROQ_MODEL,
        api_key=api_key,
        temperature=GROQ_TEMPERATURE,
        max_tokens=GROQ_MAX_TOKENS,
    )
