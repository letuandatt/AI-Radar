from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
