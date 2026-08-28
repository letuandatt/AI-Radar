"""Gemini LLM client configuration using LangChain.

This file contains ALL Gemini-specific parameters. To adjust model settings
(model name, temperature, max_tokens, etc.), modify this file only.
Do NOT dig into LangChain source code.

Provider: Google Gemini (via langchain-google-genai)
Primary Model: gemini-2.5-flash
"""

from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# GEMINI MODEL PARAMETERS — Edit here to adjust behavior
# ============================================================================
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_TEMPERATURE = 0.1  # Low = deterministic extraction
GEMINI_MAX_OUTPUT_TOKENS = 1024  # summary + topics + entities + score
GEMINI_TOP_P = 0.95  # Nucleus sampling
GEMINI_TOP_K = 40  # Top-K sampling


# ============================================================================


def create_gemini_chat_model(api_key: str) -> ChatGoogleGenerativeAI:
    """Create a configured ChatGoogleGenerativeAI instance.

    Args:
        api_key: Gemini API key (from settings/env).

    Returns:
        Configured ChatGoogleGenerativeAI instance ready for use.
    """
    logger.info(
        "Creating Gemini chat model: %s (temp=%.1f, max_tokens=%d)",
        GEMINI_MODEL,
        GEMINI_TEMPERATURE,
        GEMINI_MAX_OUTPUT_TOKENS,
    )

    return ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        google_api_key=api_key,
        temperature=GEMINI_TEMPERATURE,
        max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
        top_p=GEMINI_TOP_P,
        top_k=GEMINI_TOP_K,
    )
