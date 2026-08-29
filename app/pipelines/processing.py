"""Knowledge Processing Pipeline orchestration.

Coordinates the full flow of article processing:
Cleaning -> Normalization -> Extraction -> Assembly.
Integrates with ProcessingStateService for checkpoint/resume
and replay of failed items.
"""

import time
from collections.abc import Callable

from app.core.logger import get_logger
from app.core.utils import compute_content_hash
from app.models.article import RawArticle
from app.models.enriched_article import EnrichedArticle
from app.models.normalized_article import NormalizedArticle
from app.models.processing_result import ProcessingResult
from app.services.knowledge.object_assembler import KnowledgeObjectAssembler
from app.services.processing_state_service import ProcessingStateService

logger = get_logger(__name__)

# Stage type definitions
CleaningStage = Callable[[RawArticle], RawArticle]
NormalizationStage = Callable[[RawArticle], NormalizedArticle]
ExtractionStage = Callable[[NormalizedArticle], EnrichedArticle]


class ProcessingPipeline:
    """Orchestrates the knowledge processing pipeline.

    Processes a list of RawArticles through cleaning, normalization,
    extraction, and assembly stages. Uses ProcessingStateService
    to skip already-processed items and track failures for replay.

    Thread Safety:
        Not thread-safe. Callers are responsible for synchronization.
    """

    def __init__(
        self,
        cleaning_stage: CleaningStage,
        normalization_stage: NormalizationStage,
        extraction_stage: ExtractionStage,
        assembler: KnowledgeObjectAssembler,
        state_service: ProcessingStateService,
    ) -> None:
        """Initialize the pipeline with its stage implementations.

        Args:
            cleaning_stage: Callable that cleans a RawArticle.
            normalization_stage: Callable that normalizes a RawArticle.
            extraction_stage: Callable that extracts metadata from a NormalizedArticle.
            assembler: Service that assembles and persists KnowledgeObjects.
            state_service: Service for tracking item processing state.
        """
        self._cleaning = cleaning_stage
        self._normalization = normalization_stage
        self._extraction = extraction_stage
        self._assembler = assembler
        self._state = state_service

    def run(self, raw_articles: list[RawArticle]) -> ProcessingResult:
        """Run the full processing pipeline on a batch of articles.

        Each article is processed sequentially through 4 stages.
        If an article fails at any stage, the error is recorded,
        state is updated, and the pipeline continues with the next article.

        Args:
            raw_articles: List of raw articles to process.

        Returns:
            ProcessingResult summarizing the pipeline outcome.
        """
        start_time = time.time()

        total_input = len(raw_articles)
        cleaned = 0
        normalized = 0
        extracted = 0
        failed_objects = 0
        skipped_objects = 0
        errors: list[dict] = []

        enriched_articles: list[EnrichedArticle] = []

        for article in raw_articles:
            content_hash = compute_content_hash(article.url, article.title)

            # Check checkpoint: skip if already successfully stored
            state = self._state.get_status(content_hash)
            if state and state.status == "success" and state.stage == "stored":
                skipped_objects += 1
                logger.debug("Skipping already stored article: %s", article.url)
                continue

            current_stage = "cleaned"
            try:
                # Stage 1: Cleaning
                cleaned_article = self._cleaning(article)
                cleaned += 1
                self._state.update_status(content_hash, "cleaned", "success")

                # Stage 2: Normalization
                current_stage = "normalized"
                normalized_article = self._normalization(cleaned_article)
                normalized += 1
                self._state.update_status(content_hash, "normalized", "success")

                # Stage 3: Extraction
                current_stage = "extracted"
                enriched_article = self._extraction(normalized_article)
                extracted += 1
                self._state.update_status(content_hash, "extracted", "success")

                enriched_articles.append(enriched_article)

            except Exception as e:
                failed_objects += 1
                self._state.update_status(
                    content_hash,
                    current_stage,
                    "failed",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                errors.append(
                    {
                        "url": article.url,
                        "stage": current_stage,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    }
                )
                logger.error(
                    "Pipeline failed at %s for %s: %s",
                    current_stage,
                    article.url,
                    e,
                )

        # Stage 4: Assembly (batch processing)
        created_count = 0
        updated_count = 0
        if enriched_articles:
            assembly_result = self._assembler.assemble(enriched_articles)
            created_count = assembly_result.created_count
            updated_count = assembly_result.updated_count

            # Update state to "stored" for successfully assembled articles
            for enriched in enriched_articles:
                c_hash = compute_content_hash(enriched.article.url, enriched.article.title)
                self._state.update_status(c_hash, "stored", "success")

        # Persist state to disk
        self._state.flush()

        duration = time.time() - start_time

        result = ProcessingResult(
            total_input=total_input,
            cleaned=cleaned,
            normalized=normalized,
            extracted=extracted,
            objects_created=created_count,
            objects_updated=updated_count,
            failed_objects=failed_objects,
            skipped_objects=skipped_objects,
            processing_duration=duration,
            errors=errors,
        )

        logger.info(
            "Pipeline completed: input=%d, cleaned=%d, normalized=%d, "
            "extracted=%d, created=%d, updated=%d, failed=%d, skipped=%d, "
            "duration=%.2fs",
            result.total_input,
            result.cleaned,
            result.normalized,
            result.extracted,
            result.objects_created,
            result.objects_updated,
            result.failed_objects,
            result.skipped_objects,
            result.processing_duration,
        )

        return result

    def get_failed_articles(self, raw_articles: list[RawArticle]) -> list[RawArticle]:
        """Filter a list of articles to only those that previously failed.

        Args:
            raw_articles: List of articles to check.

        Returns:
            List of articles that have a 'failed' state.
        """
        failed = []
        for article in raw_articles:
            content_hash = compute_content_hash(article.url, article.title)
            state = self._state.get_status(content_hash)
            if state and state.status == "failed":
                failed.append(article)
        return failed

    def replay_failed(self, raw_articles: list[RawArticle]) -> ProcessingResult:
        """Re-process only items that previously failed.

        Args:
            raw_articles: Full list of articles (will be filtered to failed only).

        Returns:
            ProcessingResult for the replayed items.
        """
        failed_articles = self.get_failed_articles(raw_articles)
        if not failed_articles:
            logger.info("No failed articles to replay.")
            return ProcessingResult(total_input=0, processing_duration=0.0)

        logger.info("Replaying %d failed articles", len(failed_articles))
        return self.run(failed_articles)
