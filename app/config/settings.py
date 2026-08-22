from datetime import time
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    groq_api_key: str
    cohere_api_key: str

    qdrant_url: str
    qdrant_api_key: str

    zalo_app_id: str
    zalo_app_secret: str
    zalo_access_token: str
    zalo_webhook_secret: str

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
        default=True,
        description="Whether to run acquisition pipeline immediately on application startup.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
