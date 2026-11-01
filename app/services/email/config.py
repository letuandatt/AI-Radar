"""Optional email configuration; secrets are loaded only for email entrypoints."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.services.email.models import http_url, normalize_email


class EmailConfig(BaseSettings):
    """Read EMAIL_* variables; preview works without delivery credentials."""

    model_config = SettingsConfigDict(env_prefix="EMAIL_", env_file=".env.email", extra="ignore")
    brevo_api_key: SecretStr = SecretStr("")
    sender_email: str = ""
    sender_name: str = "AI-Radar"
    public_base_url: str = ""
    webhook_secret: SecretStr = SecretStr("")
    soft_bounce_limit: int = Field(default=3, ge=1)

    def check_delivery(self) -> None:
        """Require sender, provider credentials and a reachable HTTPS callback origin."""
        normalize_email(self.sender_email)
        http_url(self.public_base_url, https_only=True)
        if not self.brevo_api_key.get_secret_value().strip():
            raise ValueError("EMAIL_BREVO_API_KEY is required")
        if len(self.webhook_secret.get_secret_value()) < 32:
            raise ValueError("EMAIL_WEBHOOK_SECRET must contain at least 32 characters")
