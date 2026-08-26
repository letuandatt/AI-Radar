"""Raw Data Validation Service for Knowledge Processing.

This service validates the integrity of raw articles before they enter
the processing pipeline. It acts as the "first gate" to filter out noise,
malformed data, and content that would waste LLM tokens.
"""

import re
from typing import Any
from urllib.parse import urlparse

from app.core.logger import get_logger
from app.models.article import RawArticle
from app.models.validation import ValidationResult

logger = get_logger(__name__)

# Minimum title length after stripping whitespace
_MIN_TITLE_LENGTH = 10

# Regex to match HTML tags for stripping
_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


class RawDataValidator:
    """Validates the integrity of RawArticle objects.

    This validator checks three critical aspects of raw data:
    1. Title: Must be non-empty and at least 10 characters long.
    2. URL: Must be a valid URL with scheme and netloc.
    3. Content: Must contain actual text (not just HTML tags).

    Returns ValidationResult instead of raising exceptions, following
    the validation pattern established in Sprint 08 (AI-002).
    """

    def validate(self, article: RawArticle) -> ValidationResult:
        """Validate a RawArticle for processing readiness.

        Args:
            article: The raw article to validate.

        Returns:
            ValidationResult indicating whether the article is valid
            for processing, with detailed error information if not.
        """
        # Check title
        title_result = self._validate_title(article.title)
        if not title_result.is_valid:
            logger.debug(
                "Article rejected (invalid title): %s - %s",
                article.url,
                title_result.error_message,
            )
            return title_result

        # Check URL
        url_result = self._validate_url(article.url)
        if not url_result.is_valid:
            logger.debug(
                "Article rejected (invalid URL): %s - %s",
                article.url,
                url_result.error_message,
            )
            return url_result

        # Check content
        content_result = self._validate_content(article.content)
        if not content_result.is_valid:
            logger.debug(
                "Article rejected (invalid content): %s - %s",
                article.url,
                content_result.error_message,
            )
            return content_result

        logger.debug("Article validated successfully: %s", article.url)
        return ValidationResult.success(
            details={
                "url": article.url,
                "title_length": len(article.title.strip()),
                "content_length": len(article.content),
            }
        )

    def _validate_title(self, title: Any) -> ValidationResult:
        """Validate the title field.

        Rules:
        - Must be a string
        - Must not be empty after stripping whitespace
        - Must be at least 10 characters long after stripping

        Args:
            title: The title value to validate.

        Returns:
            ValidationResult indicating success or failure.
        """
        if title is None:
            return ValidationResult.failure(
                error_message="Title is missing (None)",
                details={"field": "title"},
            )

        if not isinstance(title, str):
            return ValidationResult.failure(
                error_message=f"Title must be a string, got {type(title).__name__}",
                details={"field": "title", "actual_type": type(title).__name__},
            )

        stripped_title = title.strip()

        if not stripped_title:
            return ValidationResult.failure(
                error_message="Title is empty after stripping whitespace",
                details={"field": "title", "original_length": len(title)},
            )

        if len(stripped_title) < _MIN_TITLE_LENGTH:
            return ValidationResult.failure(
                error_message=f"Title too short: {len(stripped_title)} "
                f"chars (minimum {_MIN_TITLE_LENGTH})",
                details={
                    "field": "title",
                    "actual_length": len(stripped_title),
                    "minimum_length": _MIN_TITLE_LENGTH,
                },
            )

        return ValidationResult.success()

    def _validate_url(self, url: Any) -> ValidationResult:
        """Validate the URL field.

        Rules:
        - Must be a string
        - Must be parseable by urllib
        - Must have a scheme (http/https)
        - Must have a netloc (domain)

        Args:
            url: The URL value to validate.

        Returns:
            ValidationResult indicating success or failure.
        """
        if url is None:
            return ValidationResult.failure(
                error_message="URL is missing (None)",
                details={"field": "url"},
            )

        if not isinstance(url, str):
            return ValidationResult.failure(
                error_message=f"URL must be a string, got {type(url).__name__}",
                details={"field": "url", "actual_type": type(url).__name__},
            )

        if not url.strip():
            return ValidationResult.failure(
                error_message="URL is empty",
                details={"field": "url"},
            )

        try:
            parsed = urlparse(url)
        except Exception as e:
            return ValidationResult.failure(
                error_message=f"URL parsing failed: {str(e)}",
                details={"field": "url", "url": url, "error": str(e)},
            )

        if not parsed.scheme:
            return ValidationResult.failure(
                error_message=f"URL missing scheme (http/https): {url}",
                details={"field": "url", "url": url, "parsed": str(parsed)},
            )

        if parsed.scheme not in ("http", "https"):
            return ValidationResult.failure(
                error_message=f"URL has invalid scheme '{parsed.scheme}' (expected http/https)",
                details={"field": "url", "url": url, "scheme": parsed.scheme},
            )

        if not parsed.netloc:
            return ValidationResult.failure(
                error_message=f"URL missing netloc (domain): {url}",
                details={"field": "url", "url": url, "parsed": str(parsed)},
            )

        return ValidationResult.success()

    def _validate_content(self, content: Any) -> ValidationResult:
        """Validate the content field.

        Rules:
        - Must be a string
        - Must not be empty
        - Must contain actual text (not just HTML tags)

        Args:
            content: The content value to validate.

        Returns:
            ValidationResult indicating success or failure.
        """
        if content is None:
            return ValidationResult.failure(
                error_message="Content is missing (None)",
                details={"field": "content"},
            )

        if not isinstance(content, str):
            return ValidationResult.failure(
                error_message=f"Content must be a string, got {type(content).__name__}",
                details={"field": "content", "actual_type": type(content).__name__},
            )

        if not content.strip():
            return ValidationResult.failure(
                error_message="Content is empty after stripping whitespace",
                details={"field": "content", "original_length": len(content)},
            )

        # Strip HTML tags and check if there's actual text
        text_only = self._strip_html_tags(content).strip()

        if not text_only:
            return ValidationResult.failure(
                error_message="Content contains only HTML tags, no actual text",
                details={
                    "field": "content",
                    "original_length": len(content),
                    "text_length": 0,
                },
            )

        return ValidationResult.success()

    def _strip_html_tags(self, html: str) -> str:
        """Remove HTML tags from a string.

        Uses a simple regex-based approach for speed. This is sufficient
        for our use case (checking if content has actual text), though
        not as robust as a full HTML parser.

        Args:
            html: String potentially containing HTML tags.

        Returns:
            String with HTML tags removed.
        """
        return _HTML_TAG_PATTERN.sub("", html)
