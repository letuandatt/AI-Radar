"""Subscriber policy, bounce deduplication and unsubscribe links."""

from urllib.parse import urlencode, urlsplit

from app.services.email.models import Subscriber, http_url, normalize_email
from app.storage.knowledge.email_store import EmailStore


class SubscriberService:
    """Soft bounces accumulate per distinct message; successful delivery does not reset them."""

    def __init__(self, store: EmailStore, soft_bounce_limit: int = 3) -> None:
        if soft_bounce_limit < 1:
            raise ValueError("soft_bounce_limit must be positive")
        self.store = store
        self.limit = soft_bounce_limit

    @staticmethod
    def _model(row: dict) -> Subscriber:
        return Subscriber.model_validate({k: v for k, v in row.items() if k != "unsubscribe_token"})

    def subscribe(self, email: str) -> Subscriber:
        """Register an explicitly opted-in address; never silently reactivate it."""
        return self._model(self.store.subscribe(normalize_email(email)))

    def list_active(self) -> list[Subscriber]:
        """List active recipients without exposing unsubscribe tokens."""
        return [self._model(row) for row in self.store.active()]

    def deactivate(self, email: str, reason: str = "manual") -> bool:
        """Suppress future delivery to an existing subscriber."""
        return self.store.deactivate(normalize_email(email), reason)

    def record_soft_bounce(self, email: str, message_id: str) -> bool:
        """Apply at most one increment per message, even when callbacks are replayed."""
        if not message_id.strip():
            raise ValueError("message_id is required")
        return self.store.event(normalize_email(email), message_id, "soft_bounce", self.limit)

    def handle_event(self, email: str, message_id: str, event: str) -> bool:
        """Ignore informational events; suppress hard bounces, complaints and opt-outs."""
        if event == "soft_bounce":
            return self.record_soft_bounce(email, message_id)
        if event not in {"hard_bounce", "spam", "unsubscribed", "invalid", "blocked"}:
            return False
        if not message_id.strip():
            raise ValueError("message_id is required")
        return self.store.event(normalize_email(email), message_id, event, self.limit)

    def unsubscribe_link(self, email: str, base_url: str) -> str:
        """Create an opaque per-subscriber capability URL; GET only shows confirmation."""
        http_url(base_url, https_only=True)
        origin = urlsplit(base_url)
        if origin.path not in {"", "/"} or origin.query or origin.fragment:
            raise ValueError("Public base URL must be an HTTPS origin without path or query")
        row = self.store.get(normalize_email(email))
        if row is None:
            raise LookupError("Subscriber not found")
        return (
            base_url.rstrip("/")
            + "/api/email/unsubscribe?"
            + urlencode({"token": row["unsubscribe_token"]})
        )

    def unsubscribe(self, token: str) -> bool:
        """Idempotently suppress an address selected by its opaque token."""
        return self.store.unsubscribe(token)
