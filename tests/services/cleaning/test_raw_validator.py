"""Tests for Raw Data Validation Service (T111)."""

from datetime import datetime

import pytest

from app.models.article import RawArticle
from app.services.cleaning.raw_validator import RawDataValidator


@pytest.fixture
def validator():
    """Provide a RawDataValidator instance."""
    return RawDataValidator()


@pytest.fixture
def valid_article():
    """Provide a valid RawArticle for testing."""
    return RawArticle(
        title="This is a valid article title with enough length",
        url="https://example.com/article/123",
        content="This is the content of the article. It has actual text.",
        source_name="test_source",
        published_date=datetime.now(),
    )


# ==============================================================================
# Valid Article Tests
# ==============================================================================


class TestValidArticles:
    """Tests for valid articles."""

    def test_validate_valid_article(self, validator, valid_article):
        """Verify that a fully valid article passes validation."""
        result = validator.validate(valid_article)

        assert result.is_valid is True
        assert result.error_message is None
        assert result.details["url"] == valid_article.url
        assert result.details["title_length"] == len(valid_article.title.strip())
        assert result.details["content_length"] == len(valid_article.content)

    def test_validate_article_with_html_content(self, validator):
        """Verify that articles with HTML content are valid if they have text."""
        article = RawArticle(
            title="Article with HTML content",
            url="https://example.com/article",
            content="<p>This is <strong>bold</strong> text.</p>",
            source_name="test",
            published_date=datetime.now(),
        )

        result = validator.validate(article)

        assert result.is_valid is True


# ==============================================================================
# Title Validation Tests
# ==============================================================================


class TestTitleValidation:
    """Tests for title validation rules."""

    def test_title_none(self, validator, valid_article):
        """Verify that None title fails validation."""
        article = RawArticle(
            title=None,  # type: ignore
            url=valid_article.url,
            content=valid_article.content,
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "title" in result.error_message.lower()
        assert "missing" in result.error_message.lower() or "none" in result.error_message.lower()

    def test_title_empty(self, validator, valid_article):
        """Verify that empty title fails validation."""
        article = RawArticle(
            title="   ",
            url=valid_article.url,
            content=valid_article.content,
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "empty" in result.error_message.lower()

    def test_title_too_short(self, validator, valid_article):
        """Verify that title shorter than 10 chars fails validation."""
        article = RawArticle(
            title="Short",
            url=valid_article.url,
            content=valid_article.content,
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "too short" in result.error_message.lower()
        assert result.details["actual_length"] == 5
        assert result.details["minimum_length"] == 10

    def test_title_exactly_10_chars(self, validator, valid_article):
        """Verify that title with exactly 10 chars passes validation."""
        article = RawArticle(
            title="Exactly10c",  # 10 characters
            url=valid_article.url,
            content=valid_article.content,
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is True

    def test_title_non_string(self, validator, valid_article):
        """Verify that non-string title fails validation."""
        article = RawArticle(
            title=12345,  # type: ignore
            url=valid_article.url,
            content=valid_article.content,
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "string" in result.error_message.lower()


# ==============================================================================
# URL Validation Tests
# ==============================================================================


class TestURLValidation:
    """Tests for URL validation rules."""

    def test_url_none(self, validator, valid_article):
        """Verify that None URL fails validation."""
        article = RawArticle(
            title=valid_article.title,
            url=None,  # type: ignore
            content=valid_article.content,
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "url" in result.error_message.lower()

    def test_url_empty(self, validator, valid_article):
        """Verify that empty URL fails validation."""
        article = RawArticle(
            title=valid_article.title,
            url="",
            content=valid_article.content,
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "empty" in result.error_message.lower()

    def test_url_missing_scheme(self, validator, valid_article):
        """Verify that URL without scheme fails validation."""
        article = RawArticle(
            title=valid_article.title,
            url="example.com/article",
            content=valid_article.content,
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "scheme" in result.error_message.lower()

    def test_url_invalid_scheme(self, validator, valid_article):
        """Verify that URL with invalid scheme (ftp) fails validation."""
        article = RawArticle(
            title=valid_article.title,
            url="ftp://example.com/file",
            content=valid_article.content,
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "scheme" in result.error_message.lower()
        assert "ftp" in result.error_message.lower()

    def test_url_missing_netloc(self, validator, valid_article):
        """Verify that URL without netloc fails validation."""
        article = RawArticle(
            title=valid_article.title,
            url="http://",
            content=valid_article.content,
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "netloc" in result.error_message.lower() or "domain" in result.error_message.lower()

    def test_url_https_valid(self, validator, valid_article):
        """Verify that HTTPS URL passes validation."""
        article = RawArticle(
            title=valid_article.title,
            url="https://secure.example.com/article",
            content=valid_article.content,
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is True


# ==============================================================================
# Content Validation Tests
# ==============================================================================


class TestContentValidation:
    """Tests for content validation rules."""

    def test_content_none(self, validator, valid_article):
        """Verify that None content fails validation."""
        article = RawArticle(
            title=valid_article.title,
            url=valid_article.url,
            content=None,  # type: ignore
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "content" in result.error_message.lower()

    def test_content_empty(self, validator, valid_article):
        """Verify that empty content fails validation."""
        article = RawArticle(
            title=valid_article.title,
            url=valid_article.url,
            content="",
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "empty" in result.error_message.lower()

    def test_content_only_whitespace(self, validator, valid_article):
        """Verify that whitespace-only content fails validation."""
        article = RawArticle(
            title=valid_article.title,
            url=valid_article.url,
            content="   \n\t  ",
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "empty" in result.error_message.lower()

    def test_content_only_html_tags(self, validator, valid_article):
        """Verify that HTML-only content (no text) fails validation."""
        article = RawArticle(
            title=valid_article.title,
            url=valid_article.url,
            content="<div><p></p><span></span></div>",
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "html" in result.error_message.lower()
        assert "text" in result.error_message.lower()

    def test_content_non_string(self, validator, valid_article):
        """Verify that non-string content fails validation."""
        article = RawArticle(
            title=valid_article.title,
            url=valid_article.url,
            content=12345,  # type: ignore
            source_name=valid_article.source_name,
            published_date=valid_article.published_date,
        )

        result = validator.validate(article)

        assert result.is_valid is False
        assert "string" in result.error_message.lower()


# ==============================================================================
# Early Return Tests
# ==============================================================================


class TestEarlyReturn:
    """Tests to verify early return behavior (title checked first)."""

    def test_title_fails_first(self, validator):
        """Verify that if title fails, URL and content are not checked."""
        article = RawArticle(
            title="Short",  # Invalid title
            url="invalid-url",  # Also invalid
            content="",  # Also invalid
            source_name="test",
            published_date=datetime.now(),
        )

        result = validator.validate(article)

        assert result.is_valid is False
        # Error should be about title, not URL or content
        assert "title" in result.error_message.lower()
