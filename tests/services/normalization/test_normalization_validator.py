"""Tests for Normalization Validation Service."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.normalized_article import NormalizedArticle
from app.services.normalization.normalization_validator import NormalizationValidator


@pytest.fixture
def validator():
    """Provide a NormalizationValidator instance."""
    return NormalizationValidator()


@pytest.fixture
def valid_article():
    """Provide a valid NormalizedArticle."""
    return NormalizedArticle(
        article_id="abc123def456",
        title="Valid Article Title",
        content="This is valid article content.",
        url="https://example.com/article",
        source_name="test_source",
        source_type="rss",
        author="John Doe",
        published_date=datetime(2026, 8, 25, 10, 30, 0, tzinfo=timezone.utc),
        fetched_at=datetime.now(timezone.utc),
        raw_content_hash="abc123def456",
    )


# ==============================================================================
# Valid Article Tests
# ==============================================================================


class TestValidArticles:
    """Tests for valid articles."""

    def test_validate_valid_article(self, validator, valid_article):
        """Verify that a fully valid article passes validation."""
        result = validator.validate_single(valid_article)

        assert result.is_valid is True
        assert result.error_message is None

    def test_validate_valid_batch(self, validator, valid_article):
        """Verify that a batch of valid articles all pass."""
        articles = [valid_article, valid_article, valid_article]
        result = validator.validate(articles)

        assert len(result) == 3

    def test_validate_empty_list(self, validator):
        """Verify that empty list returns empty list."""
        result = validator.validate([])
        assert result == []

    def test_validate_article_without_optional_fields(self, validator):
        """Verify that article without optional fields passes."""
        article = NormalizedArticle(
            article_id="abc123",
            title="Valid Title",
            content="Valid content",
            url="https://example.com/article",
            source_name="test",
            source_type="rss",
            # author, published_date, fetched_at are optional
            raw_content_hash="abc123",
        )
        result = validator.validate_single(article)

        assert result.is_valid is True


# ==============================================================================
# Required Fields Tests
# ==============================================================================


class TestRequiredFields:
    """Tests for required field validation."""

    def test_empty_article_id_fails(self, validator, valid_article):
        """Verify that empty article_id fails validation."""
        article = valid_article.model_copy(update={"article_id": ""})
        result = validator.validate_single(article)

        assert result.is_valid is False
        assert "article_id" in result.error_message

    def test_empty_title_fails(self, validator, valid_article):
        """Verify that empty title fails validation."""
        article = valid_article.model_copy(update={"title": ""})
        result = validator.validate_single(article)

        assert result.is_valid is False
        assert "title" in result.error_message

    def test_whitespace_only_title_fails(self, validator, valid_article):
        """Verify that whitespace-only title fails validation."""
        article = valid_article.model_copy(update={"title": "   "})
        result = validator.validate_single(article)

        assert result.is_valid is False
        assert "title" in result.error_message

    def test_empty_content_fails(self, validator, valid_article):
        """Verify that empty content fails validation."""
        article = valid_article.model_copy(update={"content": ""})
        result = validator.validate_single(article)

        assert result.is_valid is False
        assert "content" in result.error_message

    def test_empty_source_name_fails(self, validator, valid_article):
        """Verify that empty source_name fails validation."""
        article = valid_article.model_copy(update={"source_name": ""})
        result = validator.validate_single(article)

        assert result.is_valid is False
        assert "source_name" in result.error_message


# ==============================================================================
# URL Validation Tests
# ==============================================================================


class TestURLValidation:
    """Tests for URL validation."""

    def test_valid_https_url_passes(self, validator, valid_article):
        """Verify that valid HTTPS URL passes."""
        article = valid_article.model_copy(update={"url": "https://example.com/article"})
        result = validator.validate_single(article)

        assert result.is_valid is True

    def test_empty_url_fails(self, validator, valid_article):
        """Verify that empty URL fails validation."""
        article = valid_article.model_copy(update={"url": ""})
        result = validator.validate_single(article)

        assert result.is_valid is False
        assert "url" in result.error_message

    def test_url_without_scheme_fails(self, validator, valid_article):
        """Verify that URL without scheme fails validation."""
        article = valid_article.model_copy(update={"url": "example.com/article"})
        result = validator.validate_single(article)

        assert result.is_valid is False
        assert "scheme" in result.error_message

    def test_url_with_invalid_scheme_fails(self, validator, valid_article):
        """Verify that URL with invalid scheme fails validation."""
        article = valid_article.model_copy(update={"url": "ftp://example.com/file"})
        result = validator.validate_single(article)

        assert result.is_valid is False
        assert "scheme" in result.error_message

    def test_url_without_netloc_fails(self, validator, valid_article):
        """Verify that URL without netloc fails validation."""
        article = valid_article.model_copy(update={"url": "http://"})
        result = validator.validate_single(article)

        assert result.is_valid is False
        assert "netloc" in result.error_message


# ==============================================================================
# Source Type Tests
# ==============================================================================


class TestSourceType:
    """Tests for source_type validation."""

    def test_valid_source_types_pass(self, validator, valid_article):
        """Verify that all valid source types pass."""
        for source_type in ["rss", "github", "huggingface", "unknown"]:
            article = valid_article.model_copy(update={"source_type": source_type})
            result = validator.validate_single(article)
            assert result.is_valid is True, f"source_type '{source_type}' should be valid"

    def test_invalid_source_type_fails(self, validator, valid_article):
        """Verify that invalid source_type fails validation."""
        article = valid_article.model_copy(update={"source_type": "invalid_type"})
        result = validator.validate_single(article)

        assert result.is_valid is False
        assert "source_type" in result.error_message
        assert "invalid_type" in result.error_message


# ==============================================================================
# Published Date Tests
# ==============================================================================


class TestPublishedDate:
    """Tests for published_date validation."""

    def test_past_date_passes(self, validator, valid_article):
        """Verify that past date passes validation."""
        past_date = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        article = valid_article.model_copy(update={"published_date": past_date})
        result = validator.validate_single(article)

        assert result.is_valid is True

    def test_none_date_passes(self, validator, valid_article):
        """Verify that None published_date passes (optional field)."""
        article = valid_article.model_copy(update={"published_date": None})
        result = validator.validate_single(article)

        assert result.is_valid is True

    def test_future_date_fails(self, validator, valid_article):
        """Verify that future date fails validation."""
        future_date = datetime.now(timezone.utc) + timedelta(days=1)
        article = valid_article.model_copy(update={"published_date": future_date})
        result = validator.validate_single(article)

        assert result.is_valid is False
        assert "future" in result.error_message

    def test_naive_date_converted_and_validated(self, validator, valid_article):
        """Verify that naive datetime is handled correctly."""
        # Naive datetime in the past should pass
        naive_past = datetime(2020, 1, 1, 0, 0, 0)
        article = valid_article.model_copy(update={"published_date": naive_past})
        result = validator.validate_single(article)

        assert result.is_valid is True


# ==============================================================================
# Batch Validation Tests
# ==============================================================================


class TestBatchValidation:
    """Tests for batch validation behavior."""

    def test_batch_removes_invalid_articles(self, validator, valid_article):
        """Verify that invalid articles are removed from batch."""
        invalid_article = valid_article.model_copy(update={"title": ""})

        articles = [valid_article, invalid_article, valid_article]
        result = validator.validate(articles)

        assert len(result) == 2  # invalid_article removed

    def test_batch_all_invalid_returns_empty(self, validator, valid_article):
        """Verify that all-invalid batch returns empty list."""
        invalid1 = valid_article.model_copy(update={"title": ""})
        invalid2 = valid_article.model_copy(update={"url": ""})

        result = validator.validate([invalid1, invalid2])

        assert result == []

    def test_batch_logs_removed_articles(self, validator, valid_article, caplog):
        """Verify that removed articles are logged."""
        invalid_article = valid_article.model_copy(update={"title": ""})

        articles = [valid_article, invalid_article]

        with caplog.at_level("INFO"):
            validator.validate(articles)

        log_messages = [record.message for record in caplog.records]
        removal_logs = [msg for msg in log_messages if "removed" in msg.lower()]

        assert len(removal_logs) >= 1
