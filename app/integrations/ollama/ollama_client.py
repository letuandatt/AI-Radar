"""Ollama local LLM client configuration using LangChain.

This file contains ALL Ollama-specific parameters. To adjust model settings
(model name, temperature, max tokens, etc.), modify this file only.
Do NOT dig into LangChain source code.

Provider: Ollama (local, OpenAI-compatible server)
Default Model: qwen3:4b (good balance of quality + speed on 8GB RAM)

NOTE on qwen3 "thinking mode":
    qwen3 models have a built-in reasoning/thinking mode that can interfere
    with structured JSON output. We disable it via model_kwargs to keep the
    output clean and deterministic for metadata extraction.
"""

from langchain_ollama import ChatOllama

from app.core.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# OLLAMA MODEL PARAMETERS — Edit here to adjust behavior
# ============================================================================

OLLAMA_MODEL = "qwen3:1.7b"  # Đổi sang "qwen3:1.7b" nếu muốn nhanh hơn
OLLAMA_TEMPERATURE = 0.1  # Thấp = deterministic, tốt cho extraction
OLLAMA_NUM_PREDICT = 1024  # Max output tokens (summary + topics + entities + score)
OLLAMA_BASE_URL = "http://localhost:11434"

# ============================================================================


def create_ollama_chat_model(
    model: str = OLLAMA_MODEL,
    base_url: str = OLLAMA_BASE_URL,
) -> ChatOllama:
    """Create a configured ChatOllama instance for local extraction.

    Args:
        model: Ollama model name (vd: qwen3:1.7b).
        base_url: Ollama server URL. Local = http://localhost:11434,
                  Docker = http://ollama:11434.

    Returns:
        Configured ChatOllama instance ready for .with_structured_output().
    """
    logger.info(
        "Creating Ollama chat model: %s (temp=%.1f, num_predict=%d, base_url=%s)",
        model,
        OLLAMA_TEMPERATURE,
        OLLAMA_NUM_PREDICT,
        base_url,
    )

    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=OLLAMA_TEMPERATURE,
        num_predict=OLLAMA_NUM_PREDICT,
        reasoning=False,
    )
