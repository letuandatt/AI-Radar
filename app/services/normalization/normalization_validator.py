"""Normalization Validation Service for Knowledge Processing.

This service validates NormalizedArticle objects against business rules
before they proceed to metadata extraction (Sprint 11). It acts as the
final gate of the normalization pipeline.
"""

from datetime import datetime, timezone
from urllib.parse import urlparse

from app.core.logger import get_logger
from app.models.normalized_article import NormalizedArticle
from app.models.validation import ValidationResult

logger = get_logger(__name__)

# Valid source types
_VALID_SOURCE_TYPES = {"rss", "github", "huggingface", "unknown"}


class NormalizationValidator:
    """Validates NormalizedArticle objects against business rules.

    This validator performs checks that Pydantic cannot enforce automatically,
    such as:
    - URL validity (scheme + netloc)
    - source_type must be a known value
    - published_date must not be in the future

    Thread Safety:
        This class is stateless and thread-safe.
    """

    def validate(self, articles: list[NormalizedArticle]) -> list[NormalizedArticle]:
        """Validate a list of NormalizedArticles and return only valid ones.

        Args:
            articles: List of NormalizedArticles to validate.

        Returns:
            A new list containing only valid NormalizedArticles.
        """
        if not articles:
            logger.debug("NormalizationValidator received empty list, returning empty result")
            return []

        logger.info("NormalizationValidator processing %d articles", len(articles))

        valid_articles: list[NormalizedArticle] = []
        removed_count = 0

        for article in articles:
            result = self.validate_single(article)

            if result.is_valid:
                valid_articles.append(article)
            else:
                removed_count += 1
                logger.info(
                    "NormalizedArticle removed | url=%s | reason=%s",
                    article.url,
                    result.error_message,
                )

        logger.info(
            "NormalizationValidator completed: %d valid, %d removed out of %d total",
            len(valid_articles),
            removed_count,
            len(articles),
        )

        return valid_articles

    def validate_single(self, article: NormalizedArticle) -> ValidationResult:
        """Validate a single NormalizedArticle.

        Args:
            article: The NormalizedArticle to validate.

        Returns:
            ValidationResult indicating success or failure.
        """
        # 1. Validate article_id
        if not article.article_id or not article.article_id.strip():
            return ValidationResult.failure(
                error_message="article_id is empty",
                details={"field": "article_id", "url": article.url},
            )

        # 2. Validate title
        if not article.title or not article.title.strip():
            return ValidationResult.failure(
                error_message="title is empty",
                details={"field": "title", "url": article.url},
            )

        # 3. Validate content
        if not article.content or not article.content.strip():
            return ValidationResult.failure(
                error_message="content is empty",
                details={"field": "content", "url": article.url},
            )

        # 4. Validate source_name
        if not article.source_name or not article.source_name.strip():
            return ValidationResult.failure(
                error_message="source_name is empty",
                details={"field": "source_name", "url": article.url},
            )

        # 5. Validate URL
        url_result = self._validate_url(article.url)
        if not url_result.is_valid:
            return url_result

        # 6. Validate source_type
        if article.source_type not in _VALID_SOURCE_TYPES:
            return ValidationResult.failure(
                error_message=f"Invalid source_type: '{article.source_type}' "
                f"(expected one of {sorted(_VALID_SOURCE_TYPES)})",
                details={
                    "field": "source_type",
                    "actual_value": article.source_type,
                    "valid_values": sorted(_VALID_SOURCE_TYPES),
                    "url": article.url,
                },
            )

        # 7. Validate published_date (must not be in the future)
        if article.published_date is not None:
            date_result = self._validate_published_date(article.published_date)
            if not date_result.is_valid:
                return date_result

        return ValidationResult.success(
            details={
                "url": article.url,
                "article_id": article.article_id,
            }
        )

    def _validate_url(self, url: str) -> ValidationResult:
        """Validate URL has scheme and netloc.

        Args:
            url: The URL to validate.

        Returns:
            ValidationResult indicating success or failure.
        """
        if not url or not url.strip():
            return ValidationResult.failure(
                error_message="url is empty",
                details={"field": "url"},
            )

        try:
            parsed = urlparse(url)
        except Exception as e:
            return ValidationResult.failure(
                error_message=f"URL parsing failed: {str(e)}",
                details={"field": "url", "url": url},
            )

        if not parsed.scheme or parsed.scheme not in ("http", "https"):
            return ValidationResult.failure(
                error_message=f"URL has invalid scheme: '{parsed.scheme}'",
                details={"field": "url", "url": url, "scheme": parsed.scheme},
            )

        if not parsed.netloc:
            return ValidationResult.failure(
                error_message="URL missing netloc (domain)",
                details={"field": "url", "url": url},
            )

        return ValidationResult.success()

    def _validate_published_date(self, published_date: datetime) -> ValidationResult:
        """Validate that published_date is not in the future.

        Args:
            published_date: The datetime to validate.

        Returns:
            ValidationResult indicating success or failure.
        """
        now_utc = datetime.now(timezone.utc)

        # Ensure published_date is timezone-aware for comparison
        if published_date.tzinfo is None:
            published_date = published_date.replace(tzinfo=timezone.utc)

        if published_date > now_utc:
            return ValidationResult.failure(
                error_message=f"published_date is in the future: {published_date.isoformat()}",
                details={
                    "field": "published_date",
                    "published_date": published_date.isoformat(),
                    "current_utc": now_utc.isoformat(),
                },
            )

        return ValidationResult.success()
