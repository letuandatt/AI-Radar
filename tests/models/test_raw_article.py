"""Tests for RawArticle data model."""

from datetime import datetime, timezone

from app.models.article import RawArticle


def test_raw_article_creation():
    """Verify that a RawArticle can be created with all fields."""
    now = datetime.now(timezone.utc)
    article = RawArticle(
        title="Test Title",
        url="http://test.com/article",
        content="Test content",
        published_date=now,
        source_name="test_source",
    )

    assert article.title == "Test Title"
    assert article.url == "http://test.com/article"
    assert article.content == "Test content"
    assert article.published_date == now
    assert article.source_name == "test_source"


def test_raw_article_with_none_date():
    """Verify that published_date can be None."""
    article = RawArticle(
        title="No Date",
        url="http://test.com/no-date",
        content="Content",
        published_date=None,
        source_name="test_source",
    )

    assert article.published_date is None


def test_raw_article_is_immutable():
    """Verify that RawArticle is frozen (immutable)."""
    article = RawArticle(
        title="Test",
        url="http://test.com",
        content="Content",
        published_date=None,
        source_name="test_source",
    )

    import pytest

    with pytest.raises(AttributeError):
        article.title = "New Title"
