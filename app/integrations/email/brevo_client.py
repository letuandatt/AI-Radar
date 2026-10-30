"""Bounded transactional email submission; no recipient data in error messages."""

import html as html_lib
from collections.abc import Callable
from time import sleep
from uuid import uuid4

import httpx

from app.services.email.models import http_url, normalize_email


class EmailSendError(RuntimeError):
    """Unknown indicates that the provider may already have accepted the email."""

    def __init__(self, message: str, *, unknown: bool = False) -> None:
        super().__init__(message)
        self.unknown = unknown


class BrevoEmailClient:
    """Send one recipient per request, with at most three total attempts."""

    def __init__(
        self,
        api_key: str,
        *,
        sender_email: str,
        sender_name: str = "AI-Radar",
        transport: httpx.BaseTransport | None = None,
        pause: Callable[[float], None] = sleep,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Brevo API key is required")
        self._key = api_key
        self._sender = {"email": normalize_email(sender_email), "name": sender_name}
        self._transport = transport
        self._pause = pause

    def send_digest(
        self,
        to_email: str,
        subject: str,
        html: str,
        unsubscribe_link: str,
        *,
        plain: str = "",
        idempotency_key: str | None = None,
    ) -> str:
        """Return Brevo's message ID on acceptance; preserve one key across retries."""
        http_url(unsubscribe_link, https_only=True)
        if not subject.strip() or "\r" in subject or "\n" in subject or not html.strip():
            raise ValueError("Expected nonblank content and a single-line subject")
        footer = (
            '<p><a href="' + html_lib.escape(unsubscribe_link, quote=True) + '">Unsubscribe</a></p>'
        )
        html_body = (
            html.replace("</body>", footer + "</body>", 1) if "</body>" in html else html + footer
        )
        payload = {
            "sender": self._sender,
            "to": [{"email": normalize_email(to_email)}],
            "subject": subject,
            "htmlContent": html_body,
            "textContent": plain + "\n\nUnsubscribe: " + unsubscribe_link,
            "headers": {"idempotencyKey": idempotency_key or str(uuid4())},
            "tags": ["ai-radar-digest"],
        }
        unknown = False
        with httpx.Client(timeout=20, transport=self._transport, follow_redirects=False) as client:
            for attempt in range(3):
                wait = float(2**attempt)
                try:
                    response = client.post(
                        "https://api.brevo.com/v3/smtp/email",
                        json=payload,
                        headers={"api-key": self._key, "accept": "application/json"},
                    )
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    error = "Brevo connection failed"
                except httpx.TransportError:
                    unknown = True
                    error = "Brevo response unavailable; acceptance is uncertain"
                else:
                    if response.status_code == 201:
                        try:
                            message_id = response.json()["messageId"]
                            if not isinstance(message_id, str) or not message_id.strip():
                                raise ValueError("Missing message ID")
                        except (ValueError, KeyError, TypeError) as exc:
                            raise EmailSendError(
                                "Invalid Brevo acceptance response", unknown=True
                            ) from exc
                        return message_id
                    if response.status_code >= 500:
                        unknown = True
                    if response.status_code not in {429, 500, 502, 503, 504}:
                        try:
                            duplicate = response.json().get("code") == "duplicate_parameter"
                        except (ValueError, AttributeError):
                            duplicate = False
                        raise EmailSendError(
                            f"Brevo rejected request (HTTP {response.status_code})",
                            unknown=unknown or duplicate,
                        )
                    error = f"Brevo temporarily unavailable (HTTP {response.status_code})"
                    retry_after = response.headers.get("Retry-After", "")
                    if retry_after:
                        try:
                            wait = max(wait, float(retry_after))
                        except ValueError:
                            raise EmailSendError(
                                "Brevo requested a deferred retry", unknown=unknown
                            )
                        if not 0 <= wait <= 30:
                            raise EmailSendError(
                                "Brevo requested a deferred retry", unknown=unknown
                            )
                if attempt == 2:
                    raise EmailSendError(error, unknown=unknown)
                self._pause(wait)
        raise AssertionError("Unreachable")
