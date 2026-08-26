"""Data Field Mapping Service for Knowledge Processing.

This service maps RawArticle objects to the unified NormalizedArticle schema,
ensuring consistency across different source types (RSS, GitHub, HuggingFace).
"""

from datetime import datetime, timezone

from app.core.logger import get_logger
from app.core.utils import compute_content_hash
from app.models.article import RawArticle
from app.models.normalized_article import NormalizedArticle

logger = get_logger(__name__)


class FieldMapper:
    """Maps RawArticle objects to the unified NormalizedArticle schema.

    This mapper ensures that articles from different sources (RSS, GitHub,
    HuggingFace) conform to a single, consistent schema before entering
    the metadata extraction phase.

    Thread Safety:
        This class is stateless and thread-safe.
    """

    def map(self, articles: list[RawArticle]) -> list[NormalizedArticle]:
        """Map a list of RawArticles to NormalizedArticles.

        Args:
            articles: List of standardized RawArticles to map.

        Returns:
            A new list containing NormalizedArticle objects.
        """
        if not articles:
            logger.debug("FieldMapper received empty list, returning empty result")
            return []

        logger.info("FieldMapper processing %d articles", len(articles))

        normalized: list[NormalizedArticle] = []
        for article in articles:
            try:
                normalized_article = self._map_single(article)
                normalized.append(normalized_article)
            except Exception as e:
                logger.warning(
                    "Failed to map article (url=%s): %s",
                    getattr(article, "url", "unknown"),
                    e,
                )

        logger.info(
            "FieldMapper completed: %d mapped out of %d total",
            len(normalized),
            len(articles),
        )
        return normalized

    def _map_single(self, article: RawArticle) -> NormalizedArticle:
        """Map a single RawArticle to NormalizedArticle.

        Args:
            article: The RawArticle to map.

        Returns:
            A NormalizedArticle object.
        """
        # Compute deterministic article_id from URL + Title
        article_id = compute_content_hash(article.url, article.title)

        # Determine source_type
        source_type = self._get_source_type(article)

        # Extract optional fields with getattr for safety
        author = getattr(article, "author", None)
        published_date = getattr(article, "published_date", None)
        fetched_at = getattr(article, "fetched_at", None)

        # If fetched_at is not set, use current UTC time
        if fetched_at is None:
            fetched_at = datetime.now(timezone.utc)

        # Ensure published_date is UTC if it's a datetime
        if isinstance(published_date, datetime) and published_date.tzinfo is None:
            published_date = published_date.replace(tzinfo=timezone.utc)

        return NormalizedArticle(
            article_id=article_id,
            title=article.title,
            content=article.content,
            url=article.url,
            source_name=article.source_name,
            source_type=source_type,
            author=author,
            published_date=published_date,
            fetched_at=fetched_at,
            raw_content_hash=article_id,  # Same as article_id for traceability
        )

    def _get_source_type(self, article: RawArticle) -> str:
        """Determine the source type of an article.

        Tries to get source_type from the article. If not available,
        attempts to infer from source_name.

        Args:
            article: The RawArticle to inspect.

        Returns:
            Source type string: "rss", "github", "huggingface", or "unknown".
        """
        # Try direct attribute
        source_type = getattr(article, "source_type", None)
        if source_type:
            return str(source_type)

        # Try to infer from source_name
        source_name = getattr(article, "source_name", "").lower()
        if "github" in source_name:
            return "github"
        elif "hugging" in source_name or "hf" in source_name:
            return "huggingface"
        elif source_name:
            # Default to RSS for named sources without explicit type
            return "rss"

        logger.warning("Unable to determine source_type for article: %s", article.url)
        return "unknown"
