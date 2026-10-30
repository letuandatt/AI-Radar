"""Backend-only web settings. Never export this model through HTTP."""

from ipaddress import ip_address
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebConfig(BaseSettings):
    """Local by default; remote binding requires explicit authentication."""

    model_config = SettingsConfigDict(env_prefix="WEB_", env_file=".env.web", extra="ignore")
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    allowed_hosts: list[str] = ["127.0.0.1", "localhost", "[::1]"]
    origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    username: str = ""
    password: SecretStr = SecretStr("")
    docs_enabled: bool = False
    email_callbacks_enabled: bool = False
    startup_timeout: float = Field(default=15, gt=0, le=120)

    @model_validator(mode="after")
    def validate_security(self) -> Self:
        """Reject partial credentials, wildcard hosts and insecure remote binding."""
        password = self.password.get_secret_value()
        if bool(self.username) != bool(password):
            raise ValueError("Both WEB_USERNAME and WEB_PASSWORD are required")
        if password and len(password) < 16:
            raise ValueError("WEB_PASSWORD must contain at least 16 characters")
        if not self.allowed_hosts or any("*" in host for host in self.allowed_hosts):
            raise ValueError("Explicit WEB_ALLOWED_HOSTS are required")
        if self.host != "localhost" and not ip_address(self.host).is_loopback and not password:
            raise ValueError("Non-loopback binding requires authentication and HTTPS termination")
        for origin in self.origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError("Origins must be explicit HTTP(S) origins without paths")
        return self
