"""Rendering contracts with untrusted source text and bounded Markdown."""

import pytest

from app.services.digest.formatter import EmailFormatter, ZaloFormatter
from app.services.digest.models import topic_groups
from tests.services.digest.test_generator import digest_env as digest_env
from tests.services.digest.test_organizer import unordered_digest as unordered_digest
from tests.services.intelligence.conftest import environment as environment
from tests.services.intelligence.test_refiner import prepared as prepared


def test_email_escapes_and_keeps_sources(unordered_digest):
    item = unordered_digest.sections[0].items[0]
    item.title = '<script>alert("x")</script> {{7*7}}'
    original = unordered_digest.model_dump()
    formatter = EmailFormatter()
    html = formatter.format_html(unordered_digest)
    plain = formatter.format_plain(unordered_digest)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "{{7*7}}" in html and item.title in plain
    assert item.source_url in html and item.source_url in plain
    assert "Daily intelligence" in html and "Unsubscribe" not in html
    assert unordered_digest.model_dump() == original


def test_zalo_budget_links_and_order(unordered_digest):
    output = ZaloFormatter().format(unordered_digest)
    assert len(output) <= 2000
    assert "more items" in output
    assert output.index("Papers") < output.index("GitHub")
    assert output.count("](") == output.count(")\n")
    assert output == ZaloFormatter().format(unordered_digest)


def test_long_url_is_omitted_not_cut(unordered_digest):
    for section in unordered_digest.sections:
        for item in section.items:
            item.source_url = "https://example.com/" + "x" * 3000
    output = ZaloFormatter().format(unordered_digest)
    assert len(output) <= 2000 and "12 more items" in output
    assert "](" not in output


def test_empty_digest(unordered_digest):
    unordered_digest.sections = []
    unordered_digest.total_items = 0
    unordered_digest.topic_groups = topic_groups([])
    for output in (
        EmailFormatter().format_html(unordered_digest),
        EmailFormatter().format_plain(unordered_digest),
        ZaloFormatter().format(unordered_digest),
    ):
        assert "No items met" in output


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://user:pass@example.com/a"])
def test_unsafe_links_fail_closed(unordered_digest, url):
    unordered_digest.sections[0].items[0].source_url = url
    with pytest.raises(ValueError):
        EmailFormatter().format_html(unordered_digest)
