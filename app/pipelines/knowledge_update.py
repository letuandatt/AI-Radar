"""Knowledge Update orchestration (Wiring & Fix Plan A1).

Chains acquisition output into the processing pipeline so fetched articles
actually reach the Knowledge Repository. This module is the single wiring
point: application.py builds the pipeline from repository components and
schedules :func:`run_knowledge_update` as part of the acquisition job.
"""

import asyncio

from app.config.settings import Settings
from app.core.logger import get_logger
from app.integrations.llm.provider import LLMProvider
from app.models.article import RawArticle
from app.models.enriched_article import EnrichedArticle
from app.models.normalized_article import NormalizedArticle
from app.models.processing_result import ProcessingResult
from app.models.result import AcquisitionResult
from app.pipelines.processing import ProcessingPipeline
from app.services.cleaning.data_cleaner import DataCleaner
from app.services.cleaning.duplicate_detector import DuplicateDetector
from app.services.cleaning.raw_validator import RawDataValidator
from app.services.extraction.content_sanitizer import ContentSanitizer
from app.services.extraction.metadata_extractor import MetadataExtractor
from app.services.filtering.relevance_gate import RelevanceGate
from app.services.knowledge.object_assembler import KnowledgeObjectAssembler
from app.services.knowledge.object_builder import ObjectBuilder
from app.services.knowledge.object_validator import KnowledgeObjectValidator
from app.services.normalization.field_mapper import FieldMapper
from app.services.normalization.normalization_validator import NormalizationValidator
from app.services.normalization.standardizer import DataStandardizer
from app.services.processing_state_service import ProcessingStateService
from app.storage.processing_state import ProcessingStateStorage

logger = get_logger(__name__)


def build_processing_pipeline(
    initializer,
    settings: Settings,
    llm_provider: LLMProvider,
) -> ProcessingPipeline:
    """Build the processing pipeline wired to the knowledge repository.

    Composes the real stage implementations (cleaning, normalization,
    async batch extraction through the SHARED LLM provider chain) and
    persists through the repository's SQLite knowledge store.

    Args:
        initializer: Initialized RepositoryInitializer (needs sqlite_store).
        settings: Application settings.
        llm_provider: Shared LLM provider chain — extraction counts against
            the same budget and rate limiter as analysis.

    Returns:
        ProcessingPipeline ready to accept RawArticles.
    """
    cleaner = DataCleaner(RawDataValidator())
    standardizer = DataStandardizer()
    mapper = FieldMapper()
    norm_validator = NormalizationValidator()
    sanitizer = ContentSanitizer()

    extractor = MetadataExtractor(
        llm_provider=llm_provider,
        sanitizer=sanitizer,
        max_concurrent=settings.llm_max_concurrent,
    )

    state_storage = ProcessingStateStorage(file_path=settings.processing_state_path)
    state_service = ProcessingStateService(storage=state_storage)

    assembler = KnowledgeObjectAssembler(
        builder=ObjectBuilder(),
        validator=KnowledgeObjectValidator(),
        store=initializer.sqlite_store,
    )

    def cleaning_stage(article: RawArticle) -> RawArticle:
        cleaned = cleaner.clean([article])
        if not cleaned:
            raise ValueError("cleaning dropped the article")
        return cleaned[0]

    def normalization_stage(article: RawArticle) -> NormalizedArticle:
        normalized = mapper.map(standardizer.standardize([article]))
        valid = norm_validator.validate(normalized)
        if not valid:
            raise ValueError("normalization dropped the article")
        return valid[0]

    async def batch_extraction_stage(
        articles: list[NormalizedArticle],
    ) -> list[EnrichedArticle]:
        # Contract: one EnrichedArticle per input, same order.
        return await extractor.extract_batch(articles)

    gate = (
        RelevanceGate(
            min_content_length=settings.gate_min_content_length,
            max_article_age_days=settings.gate_max_article_age_days,
            topic_keywords=settings.gate_topic_keywords,
        )
        if settings.gate_enabled
        else None
    )

    logger.info(
        "Processing pipeline built: provider=%s, max_concurrent=%d, batch_size=%d",
        llm_provider.get_provider_name(),
        settings.llm_max_concurrent,
        settings.llm_batch_size,
    )

    return ProcessingPipeline(
        cleaning_stage=cleaning_stage,
        normalization_stage=normalization_stage,
        extraction_stage=None,
        assembler=assembler,
        state_service=state_service,
        batch_extraction_stage=batch_extraction_stage,
        relevance_gate=gate,
        extraction_batch_size=settings.llm_batch_size,
    )


def deduplicate_articles(articles: list[RawArticle]) -> list[RawArticle]:
    """Batch-level dedup before the per-article pipeline stages."""
    return DuplicateDetector().deduplicate(articles)


def run_knowledge_update(
    acquisition_result: AcquisitionResult,
    processing_pipeline: ProcessingPipeline,
) -> ProcessingResult | None:
    """Forward acquired articles into the processing pipeline (A1).

    Runs ONE asyncio loop for the whole batch (never per article).
    Deduplicates the batch before processing.

    Args:
        acquisition_result: Result of the acquisition run (carries articles).
        processing_pipeline: The wired processing pipeline.

    Returns:
        ProcessingResult of the processing run, None when nothing to process.
    """
    articles = deduplicate_articles(acquisition_result.articles)
    if not articles:
        logger.info("No articles acquired; skipping processing")
        return None

    logger.info("Knowledge update: forwarding %d articles to processing", len(articles))
    return asyncio.run(processing_pipeline.run_async(articles))
