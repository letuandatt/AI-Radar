"""Data Standardization Service for Knowledge Processing.

This service standardizes the format of raw articles before they are
mapped to the unified NormalizedArticle schema. It handles:
- HTML stripping (using BeautifulSoup)
- Unicode NFC normalization
- Whitespace collapsing
- Datetime parsing to UTC
"""

import dataclasses
import re
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from bs4 import BeautifulSoup

from app.core.logger import get_logger
from app.models.article import RawArticle

logger = get_logger(__name__)

# Regex to collapse multiple whitespace characters into a single space
_WHITESPACE_PATTERN = re.compile(r"\s+")

# Common datetime formats to try when parsing strings
_DATETIME_FORMATS = [
    "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601 with timezone
    "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 UTC
    "%Y-%m-%dT%H:%M:%S",  # ISO 8601 without timezone
    "%Y-%m-%d %H:%M:%S",  # Common datetime format
    "%Y-%m-%d",  # Date only
]


class DataStandardizer:
    """Standardizes the format of raw articles.

    This standardizer performs text normalization (HTML stripping, Unicode NFC,
    whitespace collapsing) and datetime parsing (to UTC) on RawArticle objects.

    The output is a new RawArticle with standardized fields. The input is not modified.

    Thread Safety:
        This class is stateless and thread-safe.
    """

    def standardize(self, articles: list[RawArticle]) -> list[RawArticle]:
        """Standardize a list of raw articles.

        Args:
            articles: List of raw articles to standardize.

        Returns:
            A new list containing standardized RawArticle objects.
        """
        if not articles:
            logger.debug("DataStandardizer received empty list, returning empty result")
            return []

        logger.info("DataStandardizer processing %d articles", len(articles))

        standardized: list[RawArticle] = []

        for article in articles:
            standardized_article = self._standardize_single(article)
            standardized.append(standardized_article)

        logger.info("DataStandardizer completed: %d articles standardized", len(standardized))
        return standardized

    def _standardize_single(self, article: RawArticle) -> RawArticle:
        """Standardize a single raw article.

        Args:
            article: The raw article to standardize.

        Returns:
            A new RawArticle with standardized fields.
        """
        updates: dict[str, Any] = {}

        # Standardize title
        if article.title:
            updates["title"] = self._standardize_text(article.title)

        # Standardize content
        if article.content:
            updates["content"] = self._standardize_content(article.content)

        # Standardize published_date
        if hasattr(article, "published_date"):
            updates["published_date"] = self._standardize_datetime(article.published_date)

        # Create new article with standardized fields
        return self._create_updated_article(article, updates)

    def _standardize_text(self, text: str) -> str:
        """Standardize a text field (title, author, etc.).

        Steps:
        1. Strip HTML tags
        2. Unicode NFC normalization
        3. Collapse whitespace
        4. Strip leading/trailing whitespace

        Args:
            text: The text to standardize.

        Returns:
            Standardized text string.
        """
        # Strip HTML tags
        text = self._strip_html(text)

        # Unicode NFC normalization
        text = unicodedata.normalize("NFC", text)

        # Collapse whitespace
        text = _WHITESPACE_PATTERN.sub(" ", text)

        # Strip leading/trailing whitespace
        text = text.strip()

        return text

    def _standardize_content(self, content: str) -> str:
        """Standardize article content.

        Similar to _standardize_text but may apply additional rules
        (e.g., preserving paragraph structure).

        Args:
            content: The content to standardize.

        Returns:
            Standardized content string.
        """
        # Strip HTML tags using BeautifulSoup
        content = self._strip_html(content)

        # Unicode NFC normalization
        content = unicodedata.normalize("NFC", content)

        # Collapse multiple newlines into single newline
        content = re.sub(r"\n{3,}", "\n\n", content)

        # Collapse multiple spaces into single space (but preserve newlines)
        lines = content.split("\n")
        lines = [_WHITESPACE_PATTERN.sub(" ", line).strip() for line in lines]
        content = "\n".join(lines)

        # Strip leading/trailing whitespace
        content = content.strip()

        return content

    def _strip_html(self, html: str) -> str:
        """Strip HTML tags from a string using BeautifulSoup.

        Args:
            html: String potentially containing HTML tags.

        Returns:
            Plain text with HTML tags removed.
        """
        if not html:
            return ""

        try:
            soup = BeautifulSoup(html, "html.parser")
            # Get text content, preserving structure
            text = soup.get_text(separator=" ", strip=True)
            return text
        except Exception as e:
            logger.warning("Failed to strip HTML: %s", e)
            # Fallback: return original text if parsing fails
            return html

    def _standardize_datetime(self, dt: Any) -> datetime | None:
        """Standardize a datetime value to UTC.

        Handles:
        - datetime objects: convert to UTC
        - string values: parse to datetime UTC
        - None: return None

        Args:
            dt: The datetime value to standardize.

        Returns:
            UTC datetime object, or None if parsing fails.
        """
        if dt is None:
            return None

        if isinstance(dt, datetime):
            return self._to_utc(dt)

        if isinstance(dt, str):
            return self._parse_datetime_string(dt)

        logger.warning("Unexpected datetime type: %s", type(dt).__name__)
        return None

    def _to_utc(self, dt: datetime) -> datetime:
        """Convert a datetime object to UTC.

        Args:
            dt: The datetime object to convert.

        Returns:
            UTC datetime object.
        """
        if dt.tzinfo is None:
            # Naive datetime: assume UTC
            return dt.replace(tzinfo=timezone.utc)
        else:
            # Aware datetime: convert to UTC
            return dt.astimezone(timezone.utc)

    def _parse_datetime_string(self, dt_str: str) -> datetime | None:
        """Parse a datetime string to UTC datetime.

        Tries multiple formats:
        1. ISO 8601 (with/without timezone)
        2. RFC 822 (RSS format)
        3. Common datetime formats

        Args:
            dt_str: The datetime string to parse.

        Returns:
            UTC datetime object, or None if parsing fails.
        """
        dt_str = dt_str.strip()

        if not dt_str:
            return None

        # Try ISO 8601 format first (Python 3.11+ supports fromisoformat with Z)
        try:
            # Handle 'Z' suffix (UTC)
            iso_str = dt_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_str)
            return self._to_utc(dt)
        except (ValueError, AttributeError):
            pass

        # Try RFC 822 format (RSS feeds)
        try:
            dt = parsedate_to_datetime(dt_str)
            return self._to_utc(dt)
        except (ValueError, TypeError):
            pass

        # Try common datetime formats
        for fmt in _DATETIME_FORMATS:
            try:
                dt = datetime.strptime(dt_str, fmt)
                return self._to_utc(dt)
            except ValueError:
                continue

        # All parsing attempts failed
        logger.warning("Failed to parse datetime string: '%s'", dt_str)
        return None

    def _create_updated_article(self, article: RawArticle, updates: dict[str, Any]) -> RawArticle:
        """Create a new RawArticle with updated fields.

        Uses duck typing to support both Pydantic models and test mocks.

        Args:
            article: The original article.
            updates: Dictionary of field updates.

        Returns:
            A new RawArticle with updated fields.

        Raises:
            TypeError: If article type is not supported.
        """
        from typing import cast

        # Duck typing: check for model_copy method (Pydantic v2)
        if hasattr(article, "model_copy") and callable(getattr(article, "model_copy", None)):
            return cast(RawArticle, article.model_copy(update=updates))

        # Fallback: dataclass
        if dataclasses.is_dataclass(article) and not isinstance(article, type):
            return cast(RawArticle, dataclasses.replace(article, **updates))

        raise TypeError(f"Unsupported article type: {type(article).__name__}")
