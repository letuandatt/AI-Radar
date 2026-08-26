"""Tests for Data Field Mapping Service."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.models.article import RawArticle
from app.models.normalized_article import NormalizedArticle
from app.services.normalization.field_mapper import FieldMapper


@pytest.fixture
def mapper():
    """Provide a FieldMapper instance."""
    return FieldMapper()


def create_mock_article(
    title: str = "Test Article Title",
    content: str = "Test article content",
    url: str = "https://example.com/article",
    source_name: str = "test_source",
    **kwargs,
) -> MagicMock:
    """Helper to create a mock RawArticle for testing."""
    article = MagicMock(spec=RawArticle)
    article.title = title
    article.content = content
    article.url = url
    article.source_name = source_name

    # Set optional fields if provided
    for key, value in kwargs.items():
        setattr(article, key, value)

    return article


# ==============================================================================
# Basic Mapping Tests
# ==============================================================================


class TestBasicMapping:
    """Tests for basic field mapping functionality."""

    def test_map_valid_article(self, mapper):
        """Verify that a valid RawArticle is mapped correctly."""
        article = create_mock_article(
            title="Test Article Title",
            content="Test content",
            url="https://example.com/article",
            source_name="test_source",
            source_type="rss",
        )

        result = mapper.map([article])

        assert len(result) == 1
        normalized = result[0]
        assert isinstance(normalized, NormalizedArticle)
        assert normalized.title == "Test Article Title"
        assert normalized.content == "Test content"
        assert normalized.url == "https://example.com/article"
        assert normalized.source_name == "test_source"
        assert normalized.source_type == "rss"

    def test_map_empty_list(self, mapper):
        """Verify that empty list returns empty list."""
        result = mapper.map([])
        assert result == []

    def test_map_multiple_articles(self, mapper):
        """Verify that multiple articles are all mapped."""
        articles = [
            create_mock_article(url="https://example.com/1", title="Article One Title"),
            create_mock_article(url="https://example.com/2", title="Article Two Title"),
            create_mock_article(url="https://example.com/3", title="Article Three Title"),
        ]

        result = mapper.map(articles)

        assert len(result) == 3


# ==============================================================================
# Article ID Tests
# ==============================================================================


class TestArticleId:
    """Tests for article_id generation."""

    def test_article_id_is_deterministic(self, mapper):
        """Verify that same URL + Title produces same article_id."""
        article1 = create_mock_article(
            url="https://example.com/article",
            title="Test Title",
        )
        article2 = create_mock_article(
            url="https://example.com/article",
            title="Test Title",
        )

        result = mapper.map([article1, article2])

        assert len(result) == 2
        assert result[0].article_id == result[1].article_id

    def test_article_id_differs_for_different_url(self, mapper):
        """Verify that different URLs produce different article_ids."""
        article1 = create_mock_article(
            url="https://example.com/article1",
            title="Test Title",
        )
        article2 = create_mock_article(
            url="https://example.com/article2",
            title="Test Title",
        )

        result = mapper.map([article1, article2])

        assert result[0].article_id != result[1].article_id

    def test_article_id_differs_for_different_title(self, mapper):
        """Verify that different titles produce different article_ids."""
        article1 = create_mock_article(
            url="https://example.com/article",
            title="Title One",
        )
        article2 = create_mock_article(
            url="https://example.com/article",
            title="Title Two",
        )

        result = mapper.map([article1, article2])

        assert result[0].article_id != result[1].article_id

    def test_raw_content_hash_matches_article_id(self, mapper):
        """Verify that raw_content_hash matches article_id."""
        article = create_mock_article()
        result = mapper.map([article])

        assert result[0].raw_content_hash == result[0].article_id


# ==============================================================================
# Optional Fields Tests
# ==============================================================================


class TestOptionalFields:
    """Tests for optional field handling."""

    def test_author_mapped_when_present(self, mapper):
        """Verify that author is mapped when present."""
        article = create_mock_article(author="John Doe")
        result = mapper.map([article])

        assert result[0].author == "John Doe"

    def test_author_none_when_missing(self, mapper):
        """Verify that author is None when missing."""
        article = create_mock_article()  # No author
        result = mapper.map([article])

        assert result[0].author is None

    def test_published_date_mapped_when_present(self, mapper):
        """Verify that published_date is mapped when present."""
        dt = datetime(2026, 8, 25, 10, 30, 0, tzinfo=timezone.utc)
        article = create_mock_article(published_date=dt)
        result = mapper.map([article])

        assert result[0].published_date == dt

    def test_published_date_none_when_missing(self, mapper):
        """Verify that published_date is None when missing."""
        article = create_mock_article()  # No published_date
        result = mapper.map([article])

        assert result[0].published_date is None

    def test_naive_published_date_converted_to_utc(self, mapper):
        """Verify that naive published_date is converted to UTC."""
        dt_naive = datetime(2026, 8, 25, 10, 30, 0)
        article = create_mock_article(published_date=dt_naive)
        result = mapper.map([article])

        assert result[0].published_date is not None
        assert result[0].published_date.tzinfo == timezone.utc

    def test_fetched_at_set_to_current_time_when_missing(self, mapper):
        """Verify that fetched_at is set to current UTC time when missing."""
        article = create_mock_article()  # No fetched_at
        result = mapper.map([article])

        assert result[0].fetched_at is not None
        assert result[0].fetched_at.tzinfo == timezone.utc


# ==============================================================================
# Source Type Tests
# ==============================================================================


class TestSourceType:
    """Tests for source_type determination."""

    def test_source_type_from_attribute(self, mapper):
        """Verify that source_type is read from article attribute."""
        article = create_mock_article(source_type="github")
        result = mapper.map([article])

        assert result[0].source_type == "github"

    def test_source_type_inferred_from_github_source_name(self, mapper):
        """Verify that source_type is inferred from source_name containing 'github'."""
        article = create_mock_article(source_name="github_fastapi")
        # Remove source_type attribute to test inference
        delattr(article, "source_type") if hasattr(article, "source_type") else None
        result = mapper.map([article])

        assert result[0].source_type == "github"

    def test_source_type_inferred_from_huggingface_source_name(self, mapper):
        """Verify that source_type is inferred from source_name containing 'hugging'."""
        article = create_mock_article(source_name="huggingface_bert")
        result = mapper.map([article])

        assert result[0].source_type == "huggingface"

    def test_source_type_defaults_to_rss_for_named_source(self, mapper):
        """Verify that source_type defaults to 'rss' for named sources without explicit type."""
        article = create_mock_article(source_name="techcrunch")
        result = mapper.map([article])

        assert result[0].source_type == "rss"

    def test_source_type_unknown_when_no_info(self, mapper):
        """Verify that source_type is 'unknown' when no information is available."""
        article = create_mock_article(source_name="")
        result = mapper.map([article])

        assert result[0].source_type == "unknown"


# ==============================================================================
# Error Handling Tests
# ==============================================================================


class TestErrorHandling:
    """Tests for error handling during mapping."""

    def test_map_skips_articles_with_missing_required_fields(self, mapper):
        """Verify that articles with missing required fields are skipped."""
        # Create an article missing 'title' (required field)
        article = MagicMock(spec=RawArticle)
        article.url = "https://example.com/article"
        article.source_name = "test"
        # Deliberately NOT setting article.title
        del article.title  # This will cause AttributeError

        result = mapper.map([article])

        # Should skip the broken article, not crash
        assert len(result) == 0

    def test_map_continues_after_error(self, mapper):
        """Verify that mapping continues after encountering an error."""
        # First article is broken, second is valid
        broken_article = MagicMock(spec=RawArticle)
        broken_article.url = "https://example.com/broken"
        del broken_article.title  # Will cause error

        valid_article = create_mock_article(
            url="https://example.com/valid",
            title="Valid Article Title",
        )

        result = mapper.map([broken_article, valid_article])

        assert len(result) == 1
        assert result[0].url == "https://example.com/valid"


# ==============================================================================
# Immutability Tests
# ==============================================================================


class TestImmutability:
    """Tests to verify input is not modified."""

    def test_map_does_not_modify_input(self, mapper):
        """Verify that input articles are not modified."""
        original_title = "Original Title"
        article = create_mock_article(title=original_title)

        mapper.map([article])

        assert article.title == original_title
