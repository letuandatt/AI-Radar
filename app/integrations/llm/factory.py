"""LLM Provider Factory - creates providers from settings."""

from pathlib import Path

from pydantic import SecretStr

from app.core.cost_tracker import CostTracker
from app.core.logger import get_logger
from app.core.rate_limiter import TokenBucket
from app.integrations.llm.groq_provider import GroqProvider
from app.integrations.llm.logger import LLMLogger
from app.integrations.llm.ollama_provider import OllamaProvider
from app.integrations.llm.provider import LLMProvider
from app.integrations.llm.provider_chain import LLMProviderChain

logger = get_logger(__name__)


class LLMProviderFactory:
    """Factory for creating LLM provider chains from settings."""

    @staticmethod
    def create(
        primary_provider: str = "ollama",
        fallback_providers: list[str] | None = None,
        db_path: Path | None = None,
        daily_budget_usd: float = 10.0,
        alert_percent: float = 0.8,
        ollama_model: str = "qwen3:4b",
        groq_model: str = "qwen/qwen3.6-27b",
        groq_api_key: SecretStr = SecretStr(""),
        rate_limit_rpm: float | None = None,
        rate_limit_wait_timeout: float = 30.0,
    ) -> LLMProviderChain:
        """
        Create an LLM provider chain.

        Args:
            primary_provider: Primary provider name (ollama, groq, openrouter, gemini).
            fallback_providers: List of fallback provider names.
            db_path: Path to SQLite database for LLM logging.
            daily_budget_usd: Daily budget in USD.
            alert_percent: Alert threshold percentage.
            ollama_model: Ollama model name.
            groq_model: Groq model name.
            groq_api_key: Groq API key.
            rate_limit_rpm: Chain-level rate limit in requests per minute
                (0/None disables the limiter).
            rate_limit_wait_timeout: Max seconds to wait for a rate limiter token.

        Returns:
            LLMProviderChain configured with requested providers.
        """
        cost_tracker = CostTracker(
            daily_budget_usd=daily_budget_usd,
            alert_percent=alert_percent,
        )

        llm_logger = None
        if db_path:
            llm_logger = LLMLogger(db_path)

        rate_limiter: TokenBucket | None = None
        if rate_limit_rpm and rate_limit_rpm > 0:
            rate_per_second = rate_limit_rpm / 60.0
            rate_limiter = TokenBucket(
                rate=rate_per_second,
                capacity=max(1.0, rate_per_second),
            )

        provider_order = [primary_provider]
        if fallback_providers:
            provider_order.extend(fallback_providers)

        providers: list[LLMProvider] = []

        for provider_name in provider_order:
            if provider_name == "ollama":
                providers.append(
                    OllamaProvider(
                        model_name=ollama_model,
                        cost_tracker=cost_tracker,
                        logger=llm_logger,
                    )
                )
            elif provider_name == "groq":
                providers.append(
                    GroqProvider(
                        model_name=groq_model,
                        api_key=groq_api_key,
                        cost_tracker=cost_tracker,
                        logger=llm_logger,
                    )
                )
            else:
                logger.warning("Unknown provider: %s, skipping", provider_name)

        if not providers:
            raise ValueError("No valid providers configured")

        logger.info(
            "LLMProviderFactory: Created chain with %d providers: %s",
            len(providers),
            [p.get_provider_name() for p in providers],
        )

        return LLMProviderChain(
            providers,
            rate_limiter=rate_limiter,
            rate_limit_wait_timeout=rate_limit_wait_timeout,
        )
