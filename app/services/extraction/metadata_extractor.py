"""Metadata Extraction Service using LLM.

This service extracts structured metadata (topics, entities, summary,
relevance_score) from NormalizedArticle objects using LLM.

Architecture:
- Uses LangChain for LLM abstraction (ARCH-002 multi-provider)
- Async processing with semaphore-based concurrency control
- Retry strategy with exponential backoff (AI-003)
- Structured output via Pydantic schema (AI-001 + AI-004)
- Content sanitization before LLM call (SEC-001)
- Prompt template with <untrusted_data> boundary (ARCH-001)
"""

import asyncio
from pathlib import Path
from typing import cast

from langchain_core.prompts import PromptTemplate

from app.core.logger import get_logger
from app.models.enriched_article import EnrichedArticle
from app.models.metadata import ExtractionResult
from app.models.normalized_article import NormalizedArticle
from app.services.extraction.content_sanitizer import ContentSanitizer

logger = get_logger(__name__)

# Path to prompt template (ARCH-001)
_PROMPT_FILE = Path("prompts/extraction/metadata.md")


class MetadataExtractor:
    """Extracts structured metadata from articles using LLM.

    This extractor uses LangChain for provider-agnostic LLM calls,
    with async processing, retry strategy, and security sanitization.

    Thread Safety:
        Uses asyncio.Semaphore for concurrency control.
        All methods are async-safe.
    """

    def __init__(
        self,
        llm,
        sanitizer: ContentSanitizer,
        max_concurrent: int = 5,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        """Initialize the MetadataExtractor.

        Args:
            llm: LangChain chat model (ChatGoogleGenerativeAI or ChatGroq).
            sanitizer: ContentSanitizer instance for SEC-001 pre-processing.
            max_concurrent: Maximum concurrent LLM calls (semaphore limit).
            max_retries: Maximum retry attempts for failed LLM calls.
            retry_base_delay: Base delay in seconds for exponential backoff.
        """
        self._sanitizer = sanitizer
        self._max_concurrent = max_concurrent
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

        # Create structured output chain with retry
        # .with_structured_output() forces LLM to return ExtractionResult schema
        # .with_retry() adds automatic retry on failure (AI-003)
        self._structured_llm = llm.with_structured_output(ExtractionResult).with_retry(
            stop_after_attempt=max_retries,
            wait_exponential_min=retry_base_delay,
        )

        # Load prompt template from file (ARCH-001)
        self._prompt = self._load_prompt_template()

        # Semaphore for concurrency control
        self._semaphore = asyncio.Semaphore(max_concurrent)

        logger.info(
            "MetadataExtractor initialized: max_concurrent=%d, max_retries=%d",
            max_concurrent,
            max_retries,
        )

    def _load_prompt_template(self) -> PromptTemplate:
        """Load prompt template from file (ARCH-001).

        Returns:
            PromptTemplate with {content_text} input variable.

        Raises:
            FileNotFoundError: If prompt file doesn't exist.
        """
        if not _PROMPT_FILE.exists():
            raise FileNotFoundError(f"Prompt template not found: {_PROMPT_FILE.absolute()}")

        prompt_text = _PROMPT_FILE.read_text(encoding="utf-8")

        return PromptTemplate(
            template=prompt_text,
            input_variables=["content_text"],
        )

    async def extract_batch(self, articles: list[NormalizedArticle]) -> list[EnrichedArticle]:
        """Extract metadata for a batch of articles (async).

        Uses asyncio.Semaphore to limit concurrent LLM calls and
        asyncio.gather for parallel execution.

        Args:
            articles: List of NormalizedArticles to process.

        Returns:
            List of EnrichedArticle with extraction results.
        """
        if not articles:
            logger.debug("MetadataExtractor received empty batch")
            return []

        logger.info("MetadataExtractor processing batch of %d articles", len(articles))

        # Create tasks with semaphore-limited concurrency
        tasks = [self._extract_with_semaphore(article) for article in articles]

        # Run all tasks concurrently, capture exceptions per-task
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build EnrichedArticle list from results
        enriched_articles: list[EnrichedArticle] = []
        success_count = 0
        failed_count = 0

        for article, result in zip(articles, results):
            if isinstance(result, Exception):
                # Extraction failed with exception
                failed_count += 1
                logger.error(
                    "[%s] Extraction failed with exception: %s",
                    article.article_id[:16],
                    str(result),
                )
                enriched_articles.append(
                    EnrichedArticle(
                        article=article,
                        extraction=None,
                        extraction_status="failed",
                        extraction_error=str(result),
                    )
                )
            elif isinstance(result, ExtractionResult):
                # Extraction succeeded
                success_count += 1
                enriched_articles.append(
                    EnrichedArticle(
                        article=article,
                        extraction=result,
                        extraction_status="success",
                    )
                )
            else:
                # Unexpected result type
                failed_count += 1
                logger.error(
                    "[%s] Unexpected extraction result type: %s",
                    article.article_id[:16],
                    type(result).__name__,
                )
                enriched_articles.append(
                    EnrichedArticle(
                        article=article,
                        extraction=None,
                        extraction_status="failed",
                        extraction_error=f"Unexpected result type: {type(result).__name__}",
                    )
                )

        logger.info(
            "MetadataExtractor batch completed: %d success, %d failed out of %d total",
            success_count,
            failed_count,
            len(articles),
        )

        return enriched_articles

    async def _extract_with_semaphore(self, article: NormalizedArticle) -> ExtractionResult:
        """Extract metadata with semaphore-limited concurrency.

        Args:
            article: The article to extract metadata from.

        Returns:
            ExtractionResult with extracted metadata.
        """
        async with self._semaphore:
            return await self.extract_single(article)

    async def extract_single(self, article: NormalizedArticle) -> ExtractionResult:
        """Extract metadata from a single article.

        Pipeline:
        1. Sanitize content (SEC-001)
        2. Build prompt with <untrusted_data> boundary
        3. Call LLM with structured output
        4. Return parsed ExtractionResult

        Args:
            article: The NormalizedArticle to extract metadata from.

        Returns:
            ExtractionResult with extracted metadata.

        Raises:
            Exception: If LLM call fails after all retries.
        """
        article_id_prefix = article.article_id[:16]

        # Step 1: Sanitize content (SEC-001 pre-processing)
        logger.info(
            "[%s] Sanitizing content (%d chars)",
            article_id_prefix,
            len(article.content),
        )
        sanitized_content = self._sanitizer.sanitize(article.content)

        logger.info(
            "[%s] Content sanitized: %d -> %d chars",
            article_id_prefix,
            len(article.content),
            len(sanitized_content),
        )

        # Step 2: Build chain (prompt | structured_llm)
        chain = self._prompt | self._structured_llm

        # Step 3: Call LLM (async)
        logger.info(
            "[%s] Calling LLM for metadata extraction",
            article_id_prefix,
        )

        result = cast(
            ExtractionResult,
            cast(object, await chain.ainvoke({"content_text": sanitized_content})),
        )

        logger.info(
            "[%s] LLM extraction completed: %d topics, %d entities, score=%.2f",
            article_id_prefix,
            len(result.topics),
            len(result.entities),
            result.relevance_score,
        )

        return result
