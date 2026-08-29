"""Service for building KnowledgeObjects from EnrichedArticles.

This service is responsible for converting EnrichedArticles
into KnowledgeObjects, filtering out failed extractions
and attaching full provenance metadata.
"""

from datetime import datetime, timezone

from app.core.logger import get_logger
from app.core.utils import compute_text_hash
from app.models.enriched_article import EnrichedArticle
from app.models.knowledge_object import KnowledgeObject

logger = get_logger(__name__)


class ObjectBuilder:
    """Constructs KnowledgeObjects from a list of EnrichedArticles.

    This builder filters out articles that failed extraction or have missing
    metadata, ensuring only high-quality knowledge enters the Knowledge Store.

    Thread Safety:
        This class is stateless and thread-safe.

    Example:
        builder = ObjectBuilder()
        kos = builder.build(enriched_articles)
        print(f"Built {len(kos)} KnowledgeObjects")
    """

    def build(self, enriched_articles: list[EnrichedArticle]) -> list[KnowledgeObject]:
        """Build KnowledgeObjects from EnrichedArticles.

        Filters out articles with:
        - extraction_status != "success"
        - extraction is None

        Args:
            enriched_articles: List of articles after metadata extraction.

        Returns:
            List of successfully built KnowledgeObjects.

        Side Effects:
            Logs debug messages for skipped articles and info message for summary.
        """
        knowledge_objects: list[KnowledgeObject] = []
        skipped_count = 0

        for enriched_article in enriched_articles:
            # Skip articles that failed extraction or have missing metadata
            if (
                enriched_article.extraction_status != "success"
                or enriched_article.extraction is None
            ):
                logger.debug(
                    f"Skipping article {enriched_article.article.url} "
                    f"(status: {enriched_article.extraction_status})"
                )
                skipped_count += 1
                continue

            article = enriched_article.article

            # Handle potentially missing fetched_at by falling back to current time
            fetched_at = article.fetched_at if article.fetched_at else datetime.now(timezone.utc)

            try:
                ko = KnowledgeObject(
                    source_type=article.source_type,
                    source_name=article.source_name,
                    external_id=article.article_id,
                    source_url=article.url,
                    content_hash=compute_text_hash(article.content),
                    fetched_at=fetched_at,
                    published_at=article.published_date,
                    parser_version="1.0.0",
                    normalizer_version="1.0.0",
                    extractor_version="1.0.0",
                    title=article.title,
                    content_text=article.content,
                    metadata=enriched_article.extraction,
                )
                knowledge_objects.append(ko)
            except Exception as e:
                logger.error(f"Failed to build KnowledgeObject for {article.url}: {e}")
                skipped_count += 1

        logger.info(
            f"Built {len(knowledge_objects)} KnowledgeObjects (Skipped {skipped_count} articles)"
        )

        return knowledge_objects
