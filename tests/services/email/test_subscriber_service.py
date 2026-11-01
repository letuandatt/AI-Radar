"""Real SQLite subscriber policy and cross-connection idempotency."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.services.email.subscriber_service import SubscriberService
from app.storage.knowledge.email_store import EmailStore


@pytest.fixture
def subscribers(tmp_path):
    path = tmp_path / "repository.db"
    path.touch()
    return SubscriberService(EmailStore(path))


def test_register_normalizes_and_never_reactivates(subscribers):
    first = subscribers.subscribe(" Reader@Example.com ")
    assert first == subscribers.subscribe("reader@example.com")
    assert first.email == "reader@example.com"
    assert "unsubscribe_token" not in first.model_dump()
    subscribers.deactivate(str(first.email))
    assert not subscribers.subscribe(str(first.email)).active
    assert subscribers.list_active() == []


def test_soft_bounces_deduplicate_and_survive_reopen(subscribers):
    subscribers.subscribe("reader@example.com")
    for i in range(3):
        assert subscribers.record_soft_bounce("reader@example.com", str(i))
        assert not subscribers.record_soft_bounce("reader@example.com", str(i))
    reopened = SubscriberService(EmailStore(subscribers.store.path))
    assert reopened.list_active() == []
    row = reopened.store.get("reader@example.com")
    assert row["soft_bounces"] == 3 and row["inactive_reason"] == "soft_bounce_limit"


@pytest.mark.parametrize("event", ["hard_bounce", "spam", "unsubscribed", "invalid", "blocked"])
def test_suppress_and_ignore_delivered(subscribers, event):
    subscribers.subscribe("reader@example.com")
    assert subscribers.handle_event("reader@example.com", "m1", event)
    assert not subscribers.handle_event("reader@example.com", "m2", "delivered")
    assert subscribers.list_active() == []


def test_unsubscribe_capability(subscribers):
    subscribers.subscribe("reader@example.com")
    link = subscribers.unsubscribe_link("reader@example.com", "https://radar.example.com")
    assert "reader" not in link
    token = link.split("token=")[1]
    assert not subscribers.unsubscribe("wrong")
    assert subscribers.unsubscribe(token) and subscribers.unsubscribe(token)
    assert subscribers.list_active() == []


def test_concurrent_claim_and_event(subscribers):
    subscribers.subscribe("reader@example.com")

    def claim(_):
        other = EmailStore(subscribers.store.path)
        return other.claim("digest", "reader@example.com")

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(value is not None for value in pool.map(claim, range(4))) == 1
        applied = list(
            pool.map(
                lambda _: subscribers.record_soft_bounce("reader@example.com", "same"), range(4)
            )
        )
    assert sum(applied) == 1


def test_invalid_email_and_unknown_recipient(subscribers):
    with pytest.raises(ValueError):
        subscribers.subscribe("not an email")
    assert not subscribers.record_soft_bounce("absent@example.com", "m1")
