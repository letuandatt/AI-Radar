from datetime import time
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    groq_api_key: SecretStr
    cohere_api_key: str

    qdrant_url: str
    qdrant_api_key: str

    zalo_app_id: str
    zalo_app_secret: str
    zalo_access_token: str
    zalo_webhook_secret: str

    # --- LLM Config ---
    llm_primary_provider: str = Field(
        default="ollama",
        description="Primary LLM provider ('ollama' or 'groq').",
    )
    llm_fallback_providers: list[str] = Field(
        default_factory=list,
        description="Fallback LLM providers, tried in order when the primary fails.",
    )
    groq_model: str = Field(
        default="qwen/qwen3.6-27b",
        description="Groq model name.",
    )
    ollama_model: str = Field(
        default="qwen3:4b",
        description="Ollama model name.",
    )
    llm_daily_budget_usd: float = Field(
        default=10.0,
        description="Daily LLM spending budget in USD.",
    )
    llm_alert_percent: float = Field(
        default=0.8,
        description="Budget alert threshold as a fraction of the daily budget (0.0-1.0).",
    )
    llm_rate_limit_rpm: float = Field(
        default=60.0,
        description="Chain-level rate limit in requests per minute (0 disables).",
    )
    llm_rate_limit_wait_timeout: float = Field(
        default=30.0,
        description="Max seconds to wait for a rate limiter token before failing a call.",
    )
    llm_max_concurrent: int = Field(
        default=4,
        description="Max concurrent LLM calls per analysis batch (semaphore limit).",
    )

    rss_sources: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of RSS sources. Each item must be a dict with 'name' and 'url' keys.",
        examples=[[{"name": "techcrunch", "url": "https://techcrunch.com/feed/"}]],
    )

    fetch_timeout: float = Field(
        default=10.0, description="Timeout in seconds for HTTP requests made by fetchers."
    )

    github_repositories: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of GitHub repositories. "
        "Each item must be a dict with 'name', 'owner', and 'repo' keys.",
        examples=[[{"name": "fastapi", "owner": "tiangolo", "repo": "fastapi"}]],
    )

    github_token: str | None = Field(
        default=None,
        description="GitHub Personal Access Token for authenticated API requests"
        " (increases rate limits).",
    )

    hf_sources: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of Hugging Face sources. "
        "Each item must be a dict with 'name', 'resource_id', "
        "and 'source_type' ('dataset' or 'model') keys.",
        examples=[
            [
                {
                    "name": "bert_base",
                    "resource_id": "google-bert/bert-base-uncased",
                    "source_type": "model",
                }
            ]
        ],
    )

    hf_token: str | None = Field(
        default=None, description="Hugging Face API Token for authenticated requests."
    )

    acquisition_schedule_time: time = Field(
        default=time(6, 0),
        description="Time of day to run acquisition pipeline (HH:MM). Default: 06:00.",
    )

    acquisition_run_on_startup: bool = Field(
        default=False,
        description="Run acquisition pipeline immediately on application startup (dev only). "
        "Startup only initializes infrastructure; ingestion is triggered by the scheduled job.",
    )

    # --- Discovery Config ---
    github_discovery_enabled: bool = Field(
        default=False,
        description="Enable GitHub discovery (trending repos + new repos by topic)",
    )

    github_discovery_topics: list[str] = Field(
        default_factory=lambda: ["llm", "agents", "rag", "machine-learning"],
        description="Topics to search for new GitHub repositories",
    )

    github_discovery_min_stars: int = Field(
        default=20,
        description="Minimum stars for discovered GitHub repos",
    )

    github_discovery_trending_since: str = Field(
        default="weekly",
        description="Trending period: daily, weekly, or monthly",
    )

    hf_discovery_enabled: bool = Field(
        default=False,
        description="Enable HuggingFace discovery (daily papers + trending)",
    )

    hf_discovery_papers_limit: int = Field(
        default=20,
        description="Maximum number of daily papers to fetch",
    )

    hf_discovery_trending_limit: int = Field(
        default=20,
        description="Maximum number of trending models/datasets to fetch",
    )

    hf_discovery_papers_date: str | None = Field(
        default=None,
        description="Specific date for papers fetch (YYYY-MM-DD). Only used when mode='by_date'. "
        "Defaults to today if None.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
