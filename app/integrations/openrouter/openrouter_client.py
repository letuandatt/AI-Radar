"""OpenRouter LLM client configuration using LangChain.

This file contains ALL OpenRouter-specific parameters. To adjust model settings
(model name, temperature, max_tokens, etc.), modify this file only.
Do NOT dig into LangChain source code.

Provider: OpenRouter (OpenAI-compatible API)
Primary Model: z-ai/glm-5.2:free (FREE tier)
"""

from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter

from app.core.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

# ============================================================================
# OPENROUTER MODEL PARAMETERS — Edit here to adjust behavior
# ============================================================================

OPENROUTER_MODEL = "z-ai/glm-5.2:free"  # Free tier model
OPENROUTER_TEMPERATURE = 0.1  # Low = deterministic extraction
OPENROUTER_MAX_TOKENS = 1024  # summary + topics + entities + score
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MAX_RETRIES = 0

# ============================================================================


def create_openrouter_chat_model() -> ChatOpenRouter:
    """Create a configured ChatOpenAI instance pointing to OpenRouter.

    Args:
        api_key: OpenRouter API key (from settings/env).

    Returns:
        Configured ChatOpenAI instance ready for use.
    """
    logger.info(
        "Creating OpenRouter chat model: %s (temp=%.1f, max_tokens=%d)",
        OPENROUTER_MODEL,
        OPENROUTER_TEMPERATURE,
        OPENROUTER_MAX_TOKENS,
    )

    return ChatOpenRouter(
        model=OPENROUTER_MODEL,
        base_url=OPENROUTER_BASE_URL,
        temperature=OPENROUTER_TEMPERATURE,
        max_tokens=OPENROUTER_MAX_TOKENS,
        max_retries=OPENROUTER_MAX_RETRIES,
    )
