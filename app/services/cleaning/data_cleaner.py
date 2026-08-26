"""Invalid Data Removal Service for Knowledge Processing.

This service filters out invalid raw articles from a list, using the
RawDataValidator to determine validity. It acts as the second gate in
the cleaning pipeline, ensuring only high-quality data proceeds to
normalization and LLM processing.
"""

from app.core.logger import get_logger
from app.models.article import RawArticle
from app.services.cleaning.raw_validator import RawDataValidator

logger = get_logger(__name__)


class DataCleaner:
    """Removes invalid raw articles from a collection.

    This cleaner iterates through a list of RawArticles, validates each one
    using the RawDataValidator, and filters out any that fail validation.

    Observability:
        Every removed article is logged with its URL and the specific
        validation error, providing a clear audit trail for debugging
        and monitoring (OBS-001 preparation).

    Thread Safety:
        This class is stateless and thread-safe. Multiple threads can
        call clean() concurrently without issues.
    """

    def __init__(self, validator: RawDataValidator) -> None:
        """Initialize the cleaner with a validator instance.

        Args:
            validator: The RawDataValidator instance used to check articles.
        """
        self._validator = validator

    def clean(self, articles: list[RawArticle]) -> list[RawArticle]:
        """Filter out invalid articles from the input list.

        Args:
            articles: List of raw articles to clean.

        Returns:
            A new list containing only valid articles. The input list
            is not modified.
        """
        if not articles:
            logger.debug("DataCleaner received empty list, returning empty result")
            return []

        valid_articles: list[RawArticle] = []
        removed_count = 0

        logger.info("DataCleaner processing %d articles", len(articles))

        for article in articles:
            validation_result = self._validator.validate(article)

            if validation_result.is_valid:
                valid_articles.append(article)
            else:
                removed_count += 1
                logger.info(
                    "Article removed | url=%s | reason=%s | details=%s",
                    article.url,
                    validation_result.error_message,
                    validation_result.details,
                )

        logger.info(
            "DataCleaner completed: %d valid, %d removed out of %d total",
            len(valid_articles),
            removed_count,
            len(articles),
        )

        return valid_articles
