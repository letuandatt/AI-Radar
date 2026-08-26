"""Tests for Data Standardization Service."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.models.article import RawArticle
from app.services.normalization.standardizer import DataStandardizer


@pytest.fixture
def standardizer():
    """Provide a DataStandardizer instance."""
    return DataStandardizer()


def create_mock_article(
    title: str = "Test Title",
    content: str = "Test content",
    published_date: str | datetime | None = "2026-08-25T10:30:00Z",
    **kwargs,
) -> MagicMock:
    """Helper to create a mock RawArticle for testing.

    Uses MagicMock to avoid dependency on the actual RawArticle structure.
    """
    article = MagicMock(spec=RawArticle)
    article.title = title
    article.content = content
    article.published_date = published_date
    article.url = kwargs.get("url", "https://example.com/article")
    article.source_name = kwargs.get("source_name", "test_source")

    # Mock model_copy for Pydantic support
    def model_copy(update):
        new_article = MagicMock(spec=RawArticle)
        new_article.title = update.get("title", title)
        new_article.content = update.get("content", content)
        new_article.published_date = update.get("published_date", published_date)
        new_article.url = update.get("url", article.url)
        new_article.source_name = update.get("source_name", article.source_name)
        return new_article

    article.model_copy = model_copy
    return article


# ==============================================================================
# HTML Stripping Tests
# ==============================================================================


class TestHTMLStripping:
    """Tests for HTML stripping functionality."""

    def test_strip_simple_html_tags(self, standardizer):
        """Verify that simple HTML tags are stripped."""
        article = create_mock_article(content="<p>Hello World</p>")
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert result[0].content == "Hello World"

    def test_strip_nested_html_tags(self, standardizer):
        """Verify that nested HTML tags are stripped."""
        article = create_mock_article(content="<div><p>Paragraph 1</p><p>Paragraph 2</p></div>")
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert "Paragraph 1" in result[0].content
        assert "Paragraph 2" in result[0].content
        assert "<" not in result[0].content
        assert ">" not in result[0].content

    def test_strip_html_entities(self, standardizer):
        """Verify that HTML entities are decoded."""
        article = create_mock_article(content="A &amp; B &lt; C")
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert "A & B < C" in result[0].content

    def test_strip_html_in_title(self, standardizer):
        """Verify that HTML is stripped from title."""
        article = create_mock_article(title="<h1>Breaking News</h1>")
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert result[0].title == "Breaking News"

    def test_empty_html_content(self, standardizer):
        """Verify that empty HTML content is handled."""
        article = create_mock_article(content="<div></div>")
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert result[0].content == ""


# ==============================================================================
# Unicode Normalization Tests
# ==============================================================================


class TestUnicodeNormalization:
    """Tests for Unicode NFC normalization."""

    def test_unicode_nfc_normalization(self, standardizer):
        """Verify that Unicode is normalized to NFC form."""
        # é can be represented as e + combining acute accent (NFD)
        # or as single character (NFC)
        article = create_mock_article(title="Café" + "\u0301")  # e + combining accent
        result = standardizer.standardize([article])

        assert len(result) == 1
        # After NFC normalization, should be single character
        assert "Café" in result[0].title

    def test_emoji_preserved(self, standardizer):
        """Verify that emoji are preserved."""
        article = create_mock_article(title="AI News 🚀")
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert "🚀" in result[0].title


# ==============================================================================
# Whitespace Normalization Tests
# ==============================================================================


class TestWhitespaceNormalization:
    """Tests for whitespace collapsing."""

    def test_collapse_multiple_spaces(self, standardizer):
        """Verify that multiple spaces are collapsed."""
        article = create_mock_article(title="Breaking    News    Today")
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert result[0].title == "Breaking News Today"

    def test_strip_leading_trailing_whitespace(self, standardizer):
        """Verify that leading/trailing whitespace is stripped."""
        article = create_mock_article(title="  Breaking News  ")
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert result[0].title == "Breaking News"

    def test_collapse_tabs_and_newlines_in_title(self, standardizer):
        """Verify that tabs and newlines are collapsed in title."""
        article = create_mock_article(title="Breaking\tNews\nToday")
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert result[0].title == "Breaking News Today"

    def test_content_preserves_paragraph_structure(self, standardizer):
        """Verify that content preserves paragraph structure."""
        article = create_mock_article(content="Paragraph 1\n\nParagraph 2\n\n\nParagraph 3")
        result = standardizer.standardize([article])

        assert len(result) == 1
        # Should collapse 3+ newlines into 2, but preserve paragraph breaks
        assert "\n\n\n" not in result[0].content
        assert "Paragraph 1" in result[0].content
        assert "Paragraph 2" in result[0].content
        assert "Paragraph 3" in result[0].content


# ==============================================================================
# Datetime Parsing Tests
# ==============================================================================


class TestDatetimeParsing:
    """Tests for datetime parsing and UTC conversion."""

    def test_parse_iso8601_utc(self, standardizer):
        """Verify that ISO 8601 UTC datetime is parsed correctly."""
        article = create_mock_article(published_date="2026-08-25T10:30:00Z")
        result = standardizer.standardize([article])

        assert len(result) == 1
        dt = result[0].published_date
        assert isinstance(dt, datetime)
        assert dt.year == 2026
        assert dt.month == 8
        assert dt.day == 25
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.tzinfo == timezone.utc

    def test_parse_iso8601_with_timezone(self, standardizer):
        """Verify that ISO 8601 with timezone is parsed and converted to UTC."""
        article = create_mock_article(published_date="2026-08-25T10:30:00+07:00")
        result = standardizer.standardize([article])

        assert len(result) == 1
        dt = result[0].published_date
        assert isinstance(dt, datetime)
        # 10:30 +07:00 = 03:30 UTC
        assert dt.hour == 3
        assert dt.minute == 30
        assert dt.tzinfo == timezone.utc

    def test_parse_rfc822_format(self, standardizer):
        """Verify that RFC 822 format (RSS) is parsed correctly."""
        article = create_mock_article(published_date="Mon, 25 Aug 2026 10:30:00 +0000")
        result = standardizer.standardize([article])

        assert len(result) == 1
        dt = result[0].published_date
        assert isinstance(dt, datetime)
        assert dt.year == 2026
        assert dt.month == 8
        assert dt.day == 25
        assert dt.tzinfo == timezone.utc

    def test_datetime_object_converted_to_utc(self, standardizer):
        """Verify that datetime objects are converted to UTC."""
        # Create a timezone-aware datetime
        from datetime import timedelta

        tz_plus7 = timezone(timedelta(hours=7))
        dt_plus7 = datetime(2026, 8, 25, 10, 30, 0, tzinfo=tz_plus7)

        article = create_mock_article(published_date=dt_plus7)
        result = standardizer.standardize([article])

        assert len(result) == 1
        dt = result[0].published_date
        assert isinstance(dt, datetime)
        assert dt.tzinfo == timezone.utc
        # 10:30 +07:00 = 03:30 UTC
        assert dt.hour == 3

    def test_naive_datetime_assumed_utc(self, standardizer):
        """Verify that naive datetime is assumed to be UTC."""
        dt_naive = datetime(2026, 8, 25, 10, 30, 0)

        article = create_mock_article(published_date=dt_naive)
        result = standardizer.standardize([article])

        assert len(result) == 1
        dt = result[0].published_date
        assert isinstance(dt, datetime)
        assert dt.tzinfo == timezone.utc
        assert dt.hour == 10  # No conversion, assumed UTC

    def test_invalid_datetime_string_returns_none(self, standardizer):
        """Verify that invalid datetime string returns None."""
        article = create_mock_article(published_date="not a valid date")
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert result[0].published_date is None

    def test_none_datetime_stays_none(self, standardizer):
        """Verify that None datetime stays None."""
        article = create_mock_article(published_date=None)
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert result[0].published_date is None

    def test_empty_datetime_string_returns_none(self, standardizer):
        """Verify that empty datetime string returns None."""
        article = create_mock_article(published_date="")
        result = standardizer.standardize([article])

        assert len(result) == 1
        assert result[0].published_date is None


# ==============================================================================
# Edge Cases Tests
# ==============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_standardize_empty_list(self, standardizer):
        """Verify that empty list returns empty list."""
        result = standardizer.standardize([])
        assert result == []

    def test_standardize_multiple_articles(self, standardizer):
        """Verify that multiple articles are all standardized."""
        articles = [
            create_mock_article(title="<p>Article 1</p>"),
            create_mock_article(title="<p>Article 2</p>"),
            create_mock_article(title="<p>Article 3</p>"),
        ]

        result = standardizer.standardize(articles)

        assert len(result) == 3
        assert result[0].title == "Article 1"
        assert result[1].title == "Article 2"
        assert result[2].title == "Article 3"

    def test_input_not_modified(self, standardizer):
        """Verify that input articles are not modified."""
        original_title = "<p>Original Title</p>"
        article = create_mock_article(title=original_title)

        standardizer.standardize([article])

        assert article.title == original_title
