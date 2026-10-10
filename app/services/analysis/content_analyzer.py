"""Content Analysis Service using LLM.

Analyzes KnowledgeObjects to extract themes, entities, sentiment,
key claims, and technical depth using structured LLM output.
"""

import asyncio
from typing import cast

from app.core.logger import get_logger
from app.integrations.llm.provider import LLMProvider
from app.prompts.builder import PromptBuilder
from app.prompts.loader import PromptLoader
from app.services.analysis.models import (
    ContentAnalysisOutput,
    ContentAnalysisResult,
)
from app.services.repository.access_service import RepositoryAccessService

logger = get_logger(__name__)

# Prompt template name (matches prompts/analytics/content_analysis.md)
_PROMPT_NAME = "analytics/content_analysis"


class ContentAnalyzer:
    """Analyzes KnowledgeObjects using LLM structured output.

    The analyzer loads unanalyzed items from the repository,
    builds prompts using the PromptBuilder, calls the LLM provider
    for structured output, validates the result, and persists it
    through the RepositoryAccessService.

    Thread Safety:
        Uses asyncio.Semaphore for concurrency control.
        All public methods are async-safe.
    """

    def __init__(
        self,
        access_service: RepositoryAccessService,
        llm_provider: LLMProvider,
        prompt_loader: PromptLoader,
        max_concurrent: int = 2,
    ) -> None:
        """Initialize the ContentAnalyzer.

        Args:
            access_service: Repository access service for read/write.
            llm_provider: LLM provider for structured output.
            prompt_loader: Prompt loader for template retrieval.
            max_concurrent: Maximum concurrent LLM calls.
        """
        self._access_service = access_service
        self._llm_provider = llm_provider
        self._prompt_loader = prompt_loader
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Load prompt template at init time (fail fast if missing)
        self._prompt_template = self._prompt_loader.load(_PROMPT_NAME)

        logger.info(
            "ContentAnalyzer initialized: max_concurrent=%d, prompt=%s",
            max_concurrent,
            _PROMPT_NAME,
        )

    async def analyze(self, knowledge_id: str) -> ContentAnalysisResult:
        """Analyze a single KnowledgeObject.

        Args:
            knowledge_id: ID of the KnowledgeObject to analyze.

        Returns:
            ContentAnalysisResult with extracted metadata.

        Raises:
            ValueError: If KnowledgeObject not found.
            ValidationError: If LLM output fails validation.
        """
        # 1. Load KnowledgeObject
        item = await asyncio.to_thread(self._access_service.get_knowledge_item, knowledge_id)
        if item is None:
            raise ValueError(f"KnowledgeObject not found: {knowledge_id}")

        # 2. Build prompt
        prompt = self._build_prompt(item.content_text)

        # 3. Call LLM (in thread pool since structured_chat is synchronous)
        logger.info(
            "Analyzing KnowledgeObject %s (title: %s)",
            knowledge_id[:16],
            item.title[:50],
        )

        output = await asyncio.to_thread(
            self._llm_provider.structured_chat,
            prompt,
            ContentAnalysisOutput,
        )
        output = cast(ContentAnalysisOutput, output)

        # 4. Validate output
        self._validate_output(output)

        # 5. Build full result
        result = ContentAnalysisResult.from_output(knowledge_id, output)

        # 6. Save
        await asyncio.to_thread(self._access_service.save_content_analysis, result)

        logger.info(
            "Analysis complete for %s: %d themes, sentiment=%s, confidence=%.2f",
            knowledge_id[:16],
            len(result.themes),
            result.sentiment,
            result.confidence,
        )

        return result

    async def analyze_batch(
        self, limit: int = 50, *, raise_on_error: bool = False
    ) -> list[ContentAnalysisResult]:
        """Analyze a batch of unanalyzed KnowledgeObjects.

        Args:
            limit: Maximum number of items to analyze.
            raise_on_error: Raise after all tasks finish if any item failed.
                Successful items remain persisted and are skipped on retry.

        Returns:
            List of successful analysis results.
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        items = await asyncio.to_thread(self._access_service.list_unanalyzed_items, limit)

        if not items:
            logger.debug("No unanalyzed items found")
            return []

        logger.info("Analyzing batch of %d items", len(items))

        tasks = [self._analyze_with_semaphore(item.id) for item in items]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Separate successes from failures
        successes: list[ContentAnalysisResult] = []
        failures = 0

        for item, result in zip(items, results):
            if isinstance(result, ContentAnalysisResult):
                successes.append(result)
            else:
                failures += 1
                logger.error(
                    "Analysis failed for %s: %s",
                    item.id[:16],
                    str(result),
                )

        logger.info(
            "Batch analysis complete: %d success, %d failed out of %d total",
            len(successes),
            failures,
            len(items),
        )

        if failures and raise_on_error:
            raise RuntimeError(
                f"Content analysis incomplete: {failures}/{len(items)} failed; "
                f"{len(successes)} successful items remain saved"
            )
        return successes

    async def _analyze_with_semaphore(self, knowledge_id: str) -> ContentAnalysisResult:
        """Analyze with semaphore-limited concurrency."""
        async with self._semaphore:
            return await self.analyze(knowledge_id)

    def _build_prompt(self, content_text: str) -> str:
        """Build the analysis prompt for a knowledge item.

        Args:
            content_text: The content text to analyze.

        Returns:
            The rendered prompt string.
        """
        builder = PromptBuilder(self._prompt_template)
        builder.with_untrusted_data(content_text)
        return builder.build()

    def _validate_output(self, output: ContentAnalysisOutput) -> None:
        """Validate LLM output beyond Pydantic schema.

        Args:
            output: The LLM output to validate.

        Raises:
            ValueError: If output fails validation.
        """
        if not output.themes:
            raise ValueError("LLM output has empty themes list")

        if not output.key_claims:
            raise ValueError("LLM output has empty key_claims list")

        if output.confidence < 0.1:
            logger.warning("Very low confidence score: %.2f", output.confidence)
