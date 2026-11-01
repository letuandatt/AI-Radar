"""Email contracts and canonical addresses; validation never queries DNS."""

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, EmailStr, Field, TypeAdapter


def normalize_email(value: str) -> str:
    """Use case-insensitive subscriber identity for this application."""
    return str(TypeAdapter(EmailStr).validate_python(value.strip())).lower()


def http_url(value: str, *, https_only: bool = False) -> str:
    """Reject unsafe schemes, credentials and control characters in output links."""
    parsed = urlsplit(value)
    schemes = {"https"} if https_only else {"http", "https"}
    if (
        parsed.scheme not in schemes
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or any(c.isspace() or ord(c) < 32 for c in value)
    ):
        raise ValueError("Expected a valid HTTP(S) URL without credentials or whitespace")
    return value


class Subscriber(BaseModel):
    """Persisted state; registering again never silently reactivates a subscriber."""

    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    active: bool
    soft_bounces: int = Field(ge=0)
    inactive_reason: str | None
    created_at: str


class DeliveryOutcome(BaseModel):
    """Accepted means provider acceptance, not confirmed inbox delivery."""

    recipient: str
    status: str
    message_id: str | None = None
    error: str | None = None
