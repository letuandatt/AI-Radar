"""Tests for Source data models."""

import pytest

from app.models.source import RSSSource


def test_rss_source_creation():
    """Verify that an RSSSource can be created with required fields."""
    source = RSSSource(name="tech_crunch", url="https://techcrunch.com/feed/")

    assert source.name == "tech_crunch"
    assert source.url == "https://techcrunch.com/feed/"
    assert source.is_active is True  # Default value


def test_rss_source_inactive():
    """Verify that an RSSSource can be explicitly set to inactive."""
    source = RSSSource(name="old_blog", url="http://old.com/rss", is_active=False)

    assert source.is_active is False


def test_rss_source_is_immutable():
    """Verify that RSSSource is frozen (immutable) to prevent accidental modification."""
    source = RSSSource(name="test", url="http://test.com")

    with pytest.raises(AttributeError):
        source.name = "new_name"
