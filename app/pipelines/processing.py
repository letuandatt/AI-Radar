"""Knowledge Processing Pipeline orchestration.

Coordinates the full flow of article processing:
Cleaning -> Normalization -> Extraction -> Assembly.
Integrates with ProcessingStateService for checkpoint/resume
and replay of failed items.
"""

import time
from collections.abc import Awaitable, Callable

from app.core.logger import get_logger
from app.core.utils import compute_content_hash
from app.models.article import RawArticle
from app.models.enriched_article import EnrichedArticle
from app.models.normalized_article import NormalizedArticle
from app.models.processing_result import ProcessingResult
from app.services.filtering.relevance_gate import RelevanceGate
from app.services.knowledge.object_assembler import KnowledgeObjectAssembler
from app.services.processing_state_service import ProcessingStateService

logger = get_logger(__name__)

# Stage type definitions
CleaningStage = Callable[[RawArticle], RawArticle]
NormalizationStage = Callable[[RawArticle], NormalizedArticle]
ExtractionStage = Callable[[NormalizedArticle], EnrichedArticle]
# Async batch extraction (e.g. MetadataExtractor.extract_batch): called ONCE
# per run over the post-normalization candidate list. Must return one
# EnrichedArticle per input, in the same order (Wiring & Fix Plan A5).
BatchExtractionStage = Callable[[list[NormalizedArticle]], Awaitable[list[EnrichedArticle]]]

# Checkpoint statuses that mean "this article is already in the repository"
# ("skipped" at any stage = terminal skip: filtered, extraction-skipped, ...)


class ProcessingPipeline:
    """Orchestrates the knowledge processing pipeline.

    Processes a list of RawArticles through cleaning, normalization,
    extraction, and assembly stages. Uses ProcessingStateService
    to skip already-processed items and track failures for replay.

    Two extraction modes are supported (A5):
    - ``batch_extraction_stage``: async batch callable invoked ONCE per run
      on the candidate list (preferred — keeps async batching benefits).
    - ``extraction_stage``: sync per-article callable (test fallback).
    At least one must be provided.

    Thread Safety:
        Not thread-safe. Callers are responsible for synchronization.
    """

    def __init__(
        self,
        cleaning_stage: CleaningStage,
        normalization_stage: NormalizationStage,
        extraction_stage: ExtractionStage | None,
        assembler: KnowledgeObjectAssembler,
        state_service: ProcessingStateService,
        batch_extraction_stage: BatchExtractionStage | None = None,
        relevance_gate: RelevanceGate | None = None,
        extraction_batch_size: int = 50,
    ) -> None:
        """Initialize the pipeline with its stage implementations.

        Args:
            cleaning_stage: Callable that cleans a RawArticle.
            normalization_stage: Callable that normalizes a RawArticle.
            extraction_stage: Callable that extracts metadata from a
                NormalizedArticle (sync per-article mode). Optional when
                batch_extraction_stage is provided.
            assembler: Service that assembles and persists KnowledgeObjects.
            state_service: Service for tracking item processing state.
            batch_extraction_stage: Async batch extraction callable, invoked
                once per chunk of the candidate list (bounded batches).
            relevance_gate: Optional deterministic pre-LLM filter (C1) —
                applied between normalization and extraction in run_async().
            extraction_batch_size: Chunk size for bounded batch extraction.
        """
        if extraction_stage is None and batch_extraction_stage is None:
            raise ValueError(
                "ProcessingPipeline requires extraction_stage or batch_extraction_stage"
            )
        if extraction_batch_size < 1:
            raise ValueError("extraction_batch_size must be >= 1")
        self._cleaning = cleaning_stage
        self._normalization = normalization_stage
        self._extraction = extraction_stage
        self._batch_extraction = batch_extraction_stage
        self._assembler = assembler
        self._state = state_service
        self._relevance_gate = relevance_gate
        self._extraction_batch_size = extraction_batch_size

    def run(self, raw_articles: list[RawArticle]) -> ProcessingResult:
        """Run the full processing pipeline on a batch of articles (sync).

        If an article fails at any stage, the error is recorded,
        state is updated, and the pipeline continues with the next article.

        Args:
            raw_articles: List of raw articles to process.

        Returns:
            ProcessingResult summarizing the pipeline outcome.
        """
        extraction_stage = self._extraction
        if extraction_stage is None:
            raise ValueError("run() requires a sync extraction_stage; use run_async() instead")

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

            # Checkpoint: skip if the article is already in the repository
            state = self._state.get_status(content_hash)
            if state and (
                state.status == "skipped" or (state.status == "success" and state.stage == "stored")
            ):
                skipped_objects += 1
                logger.debug("Skipping already processed article: %s", article.url)
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

                # Stage 3: Extraction (sync per-article)
                current_stage = "extracted"
                enriched_article = extraction_stage(normalized_article)
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

        # Stage 4: Assembly + honest checkpoint marking (A4)
        created_count, updated_count, stored_failures = self._assemble_and_mark(
            enriched_articles, errors
        )
        failed_objects += stored_failures

        self._state.flush()

        return self._build_result(
            start_time=start_time,
            total_input=total_input,
            cleaned=cleaned,
            normalized=normalized,
            extracted=extracted,
            created_count=created_count,
            updated_count=updated_count,
            failed_objects=failed_objects,
            skipped_objects=skipped_objects,
            errors=errors,
        )

    async def run_async(self, raw_articles: list[RawArticle]) -> ProcessingResult:
        """Run the pipeline with async batch extraction (A5).

        Deterministic stages (cleaning, normalization) run sync per article;
        extraction runs ONCE as an async batch over the candidate list —
        never ``asyncio.run`` per article. Assembly then proceeds sync with
        per-item checkpoint marking.

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
        filtered_objects = 0
        created_count = 0
        updated_count = 0
        errors: list[dict] = []

        enriched_articles: list[EnrichedArticle] = []
        candidates: list[tuple[str, NormalizedArticle]] = []

        # Phase 1+2: cleaning and normalization (deterministic, sync)
        for article in raw_articles:
            content_hash = compute_content_hash(article.url, article.title)

            state = self._state.get_status(content_hash)
            if state and (
                state.status == "skipped" or (state.status == "success" and state.stage == "stored")
            ):
                skipped_objects += 1
                logger.debug("Skipping already processed article: %s", article.url)
                continue

            current_stage = "cleaned"
            try:
                cleaned_article = self._cleaning(article)
                cleaned += 1
                self._state.update_status(content_hash, "cleaned", "success")

                current_stage = "normalized"
                normalized_article = self._normalization(cleaned_article)
                normalized += 1
                self._state.update_status(content_hash, "normalized", "success")

                candidates.append((content_hash, normalized_article))

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

        # Phase 3: relevance gate (C1) — deterministic, before any LLM call
        if candidates and self._relevance_gate is not None:
            kept, filtered = self._relevance_gate.filter(
                [normalized for _, normalized in candidates]
            )
            kept_urls = {article.url for article in kept}
            for item in filtered:
                for c_hash, norm in candidates:
                    if norm.url == item.url:
                        self._state.update_status(c_hash, "filtered", "skipped")
                        break
            candidates = [
                (content_hash, normalized)
                for content_hash, normalized in candidates
                if normalized.url in kept_urls
            ]
            filtered_objects = len(filtered)

        # Phase 4: bounded-batch extraction (C2) — chunk the candidate list so
        # task creation is bounded and checkpoints flush after every chunk.
        if candidates and self._batch_extraction is not None:
            for chunk_start in range(0, len(candidates), self._extraction_batch_size):
                chunk = candidates[chunk_start : chunk_start + self._extraction_batch_size]
                chunk_extracted, batch_failures = await self._extract_batch_and_mark(
                    chunk, enriched_articles, errors
                )
                extracted += chunk_extracted
                failed_objects += batch_failures

                # Assembly per chunk + flush: crash mid-run keeps finished chunks
                chunk_created, chunk_updated, stored_failures = self._assemble_and_mark(
                    enriched_articles, errors
                )
                created_count += chunk_created
                updated_count += chunk_updated
                failed_objects += stored_failures
                enriched_articles = []
                self._state.flush()
        elif candidates:
            # Sync fallback: per-article extraction stage (no chunking needed)
            extraction_stage = self._extraction
            assert extraction_stage is not None, (
                "constructor guarantees a sync stage when no batch stage is set"
            )
            for content_hash, normalized_article in candidates:
                try:
                    enriched_article = extraction_stage(normalized_article)
                    extracted += 1
                    self._state.update_status(content_hash, "extracted", "success")
                    enriched_articles.append(enriched_article)
                except Exception as e:
                    failed_objects += 1
                    self._state.update_status(
                        content_hash,
                        "extracted",
                        "failed",
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
                    errors.append(
                        {
                            "url": normalized_article.url,
                            "stage": "extracted",
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        }
                    )
                    logger.error("Extraction failed for %s: %s", normalized_article.url, e)

            created_count, updated_count, stored_failures = self._assemble_and_mark(
                enriched_articles, errors
            )
            failed_objects += stored_failures

        self._state.flush()

        return self._build_result(
            start_time=start_time,
            total_input=total_input,
            cleaned=cleaned,
            normalized=normalized,
            extracted=extracted,
            created_count=created_count,
            updated_count=updated_count,
            failed_objects=failed_objects,
            skipped_objects=skipped_objects,
            filtered_objects=filtered_objects,
            errors=errors,
        )

    async def _extract_batch_and_mark(
        self,
        candidates: list[tuple[str, NormalizedArticle]],
        enriched_articles: list[EnrichedArticle],
        errors: list[dict],
    ) -> tuple[int, int]:
        """Run the async batch extraction stage and mark per-item state.

        Articles reported with extraction_status "skipped" (e.g. content too
        short) get a "skipped" checkpoint — they are not failures and cost no
        LLM call on re-runs. Genuine failures get a "failed" checkpoint.

        Returns:
            Tuple (extracted_count, failed_count).
        """
        assert self._batch_extraction is not None
        enriched_list = await self._batch_extraction([normalized for _, normalized in candidates])

        extracted = 0
        failed = 0

        for (content_hash, _), enriched in zip(candidates, enriched_list):
            if enriched.extraction_status == "success" and enriched.extraction is not None:
                extracted += 1
                self._state.update_status(content_hash, "extracted", "success")
                enriched_articles.append(enriched)
            elif enriched.extraction_status == "skipped":
                self._state.update_status(content_hash, "extracted", "skipped")
                logger.debug(
                    "Extraction skipped for %s: %s",
                    enriched.article.url,
                    enriched.extraction_error,
                )
            else:
                failed += 1
                self._state.update_status(
                    content_hash,
                    "extracted",
                    "failed",
                    error_type="ExtractionFailed",
                    error_message=enriched.extraction_error or "extraction failed",
                )
                errors.append(
                    {
                        "url": enriched.article.url,
                        "stage": "extracted",
                        "error_type": "ExtractionFailed",
                        "error_message": enriched.extraction_error or "extraction failed",
                    }
                )
                logger.error(
                    "Extraction failed for %s: %s",
                    enriched.article.url,
                    enriched.extraction_error,
                )

        return extracted, failed

    def _assemble_and_mark(
        self, enriched_articles: list[EnrichedArticle], errors: list[dict]
    ) -> tuple[int, int, int]:
        """Run assembly and update checkpoint state per item (A4).

        Invariant: the checkpoint may say "stored" only when the
        KnowledgeObject is really in the repository — i.e. the item-level
        persistence status is "created", "updated" or "skipped" (content
        unchanged). Failed persistence is recorded as failed so the next
        run replays the article instead of silently skipping it.

        Returns:
            Tuple (created, updated, failed) counts.
        """
        if not enriched_articles:
            return 0, 0, 0

        assembly_result = self._assembler.assemble(enriched_articles)
        created = 0
        updated = 0
        failed = 0

        for item in assembly_result.items:
            if item.status in ("created", "updated"):
                self._state.update_status(item.content_hash, "stored", "success")
                if item.status == "created":
                    created += 1
                else:
                    updated += 1
            elif item.status == "skipped":
                self._state.update_status(item.content_hash, "stored", "skipped")
            else:
                failed += 1
                self._state.update_status(
                    item.content_hash,
                    "stored",
                    "failed",
                    error_type="PersistenceError",
                    error_message=item.error or "unknown persistence error",
                )
                errors.append(
                    {
                        "url": item.url,
                        "stage": "stored",
                        "error_type": "PersistenceError",
                        "error_message": item.error or "unknown persistence error",
                    }
                )
                logger.error("Persistence failed for %s: %s", item.url, item.error)

        return created, updated, failed

    def _build_result(
        self,
        start_time: float,
        total_input: int,
        cleaned: int,
        normalized: int,
        extracted: int,
        created_count: int,
        updated_count: int,
        failed_objects: int,
        skipped_objects: int,
        errors: list[dict],
        filtered_objects: int = 0,
    ) -> ProcessingResult:
        """Build the ProcessingResult and log the run summary."""
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
            filtered_objects=filtered_objects,
            processing_duration=duration,
            errors=errors,
        )

        logger.info(
            "Pipeline completed: input=%d, cleaned=%d, normalized=%d, "
            "extracted=%d, created=%d, updated=%d, failed=%d, skipped=%d, "
            "filtered=%d, duration=%.2fs",
            result.total_input,
            result.cleaned,
            result.normalized,
            result.extracted,
            result.objects_created,
            result.objects_updated,
            result.failed_objects,
            result.skipped_objects,
            result.filtered_objects,
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
