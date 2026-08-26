"""Duplicate Data Detection Service for Knowledge Processing.

This service detects and removes duplicate articles from a collection using
content hashing. It uses a pragmatic approach (SHA-256 on URL + Title) to
achieve O(N) performance, suitable for the v0.3 release.
"""

from app.core.logger import get_logger
from app.core.utils import compute_content_hash
from app.models.article import RawArticle

logger = get_logger(__name__)


class DuplicateDetector:
    """Detects and removes duplicate articles from a collection.

    Uses content hashing (SHA-256 of normalized URL + Title) to identify
    duplicates. The first occurrence of each unique article is kept.

    Performance:
        - Time complexity: O(N) where N is the number of articles
        - Space complexity: O(N) for the hash set

    Thread Safety:
        This class is stateless and thread-safe.
    """

    def deduplicate(self, articles: list[RawArticle]) -> list[RawArticle]:
        """Remove duplicate articles from the input list.

        Args:
            articles: List of articles to deduplicate.

        Returns:
            A new list containing only unique articles. The first occurrence
            of each unique article is kept. The input list is not modified.
        """
        if not articles:
            logger.debug("DuplicateDetector received empty list, returning empty result")
            return []

        seen_hashes: set[str] = set()
        unique_articles: list[RawArticle] = []
        duplicate_count = 0

        logger.info("DuplicateDetector processing %d articles", len(articles))

        for article in articles:
            content_hash = compute_content_hash(article.url, article.title)

            if content_hash in seen_hashes:
                duplicate_count += 1
                logger.info(
                    "Duplicate detected | url=%s | title=%s | hash=%s",
                    article.url,
                    article.title,
                    content_hash[:16],
                )
            else:
                seen_hashes.add(content_hash)
                unique_articles.append(article)

        logger.info(
            "DuplicateDetector completed: %d unique, %d duplicates removed out of %d total",
            len(unique_articles),
            duplicate_count,
            len(articles),
        )

        return unique_articles
