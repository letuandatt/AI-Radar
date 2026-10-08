"""Architecture guard: business services must use the LLMProvider protocol.

No service/pipeline may import concrete providers or raw model factories —
all LLM calls go through LLMProviderChain (built only by the factory).
"""

from pathlib import Path

FORBIDDEN_SYMBOLS = (
    "GroqProvider",
    "OllamaProvider",
    "create_groq_chat_model",
    "create_ollama_chat_model",
)

# Provider internals + the factory are the only places allowed to know them.
ALLOWED_FILES = {
    "factory.py",
    "groq_provider.py",
    "ollama_provider.py",
    "groq_client.py",
    "ollama_client.py",
}


def test_business_services_do_not_import_concrete_providers() -> None:
    violations: list[str] = []

    for py_file in Path("app").rglob("*.py"):
        if py_file.name in ALLOWED_FILES or py_file.name == "__init__.py":
            continue
        text = py_file.read_text(encoding="utf-8")
        for symbol in FORBIDDEN_SYMBOLS:
            if symbol in text:
                violations.append(f"{py_file}: references '{symbol}'")

    assert not violations, (
        "LLM boundary violation — use LLMProvider/LLMProviderChain instead: "
        + "; ".join(violations)
    )
