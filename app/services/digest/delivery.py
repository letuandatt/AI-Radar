"""Deliver an already saved digest; never ingest, score or regenerate content."""

from app.core.logger import get_logger
from app.integrations.email.brevo_client import BrevoEmailClient, EmailSendError
from app.pipelines.daily_digest import NotificationChannel
from app.services.digest.formatter import EmailFormatter, ZaloFormatter
from app.services.digest.models import DailyDigest
from app.services.email.models import DeliveryOutcome, Subscriber, normalize_email
from app.services.email.subscriber_service import SubscriberService

logger = get_logger(__name__)


class DigestDeliveryService:
    """Sync API; async consumers must offload delivery with asyncio.to_thread."""

    def __init__(
        self,
        subscribers: SubscriberService,
        client: BrevoEmailClient,
        public_base_url: str,
        channel: NotificationChannel | None = None,
    ) -> None:
        self.subscribers = subscribers
        self.client = client
        self.base_url = public_base_url
        self.channel = channel

    def deliver_to_zalo(self, digest: DailyDigest) -> DeliveryOutcome:
        """Use the existing channel protocol; no live Zalo adapter is assumed."""
        if self.channel is None:
            return DeliveryOutcome(recipient="zalo", status="not_configured")
        try:
            sent = self.channel.send(ZaloFormatter().format(digest))
            return DeliveryOutcome(
                recipient=self.channel.name, status="accepted" if sent else "failed"
            )
        except Exception:
            return DeliveryOutcome(
                recipient=self.channel.name, status="failed", error="Channel failed"
            )

    def deliver_to_email(
        self,
        digest: DailyDigest,
        subscribers: list[Subscriber],
    ) -> list[DeliveryOutcome]:
        """Skip accepted/in-flight/ambiguous submissions and recheck current opt-outs."""
        formatter = EmailFormatter()
        html, plain = formatter.format_html(digest), formatter.format_plain(digest)
        results = []
        emails = dict.fromkeys(normalize_email(str(s.email)) for s in subscribers)
        for email in emails:
            link = self.subscribers.unsubscribe_link(email, self.base_url)
            key = self.subscribers.store.claim(digest.digest_id, email)
            if key is None:
                row = self.subscribers.store.delivery(digest.digest_id, email)
                current = self.subscribers.store.get(email)
                status = row["status"] if row and current and current["active"] else "inactive"
                results.append(DeliveryOutcome(recipient=email, status=status))
                continue
            logger.info("Email submission START: digest=%s, attempt=%s", digest.digest_id, key)
            try:
                message_id = self.client.send_digest(
                    email,
                    f"AI-Radar Digest · {digest.digest_date}",
                    html,
                    link,
                    plain=plain,
                    idempotency_key=key,
                )
                result = DeliveryOutcome(recipient=email, status="accepted", message_id=message_id)
            except EmailSendError as exc:
                result = DeliveryOutcome(
                    recipient=email, status="unknown" if exc.unknown else "failed", error=str(exc)
                )
            except Exception:
                result = DeliveryOutcome(
                    recipient=email, status="unknown", error="Submission interrupted"
                )
            self.subscribers.store.finish(key, result.status, result.message_id)
            logger.info("Email submission DONE: attempt=%s, status=%s", key, result.status)
            results.append(result)
        return results

    def deliver_all(self, digest: DailyDigest) -> list[DeliveryOutcome]:
        """Deliver through configured channels; failures remain explicit per recipient."""
        results = self.deliver_to_email(digest, self.subscribers.list_active())
        if self.channel is not None:
            results.append(self.deliver_to_zalo(digest))
        return results
