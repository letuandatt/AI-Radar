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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
