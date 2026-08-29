# app/services/knowledge/object_assembler.py
"""Orchestrator service for the Knowledge Object assembly pipeline.

Coordinates the full flow: build → validate → persist.
This is the top-level entry point that the pipeline scheduler
will invoke to process enriched articles into stored knowledge.
"""

from dataclasses import dataclass

from app.core.logger import get_logger
from app.models.enriched_article import EnrichedArticle
from app.services.knowledge.object_builder import ObjectBuilder
from app.services.knowledge.object_validator import KnowledgeObjectValidator
from app.storage.knowledge_store import KnowledgeStore

logger = get_logger(__name__)


@dataclass(frozen=True)
class AssemblyResult:
    """Summary of an assembly pipeline run.

    Attributes:
        total_input: Number of EnrichedArticles received.
        built_count: Number of KnowledgeObjects successfully built.
        valid_count: Number of objects that passed validation.
        invalid_count: Number of objects that failed validation.
        created_count: Number of new objects persisted.
        updated_count: Number of existing objects updated.
    """

    total_input: int
    built_count: int
    valid_count: int
    invalid_count: int
    created_count: int
    updated_count: int


class KnowledgeObjectAssembler:
    """Orchestrates the full assembly pipeline: build → validate → persist.

    This service wires together ObjectBuilder, KnowledgeObjectValidator,
    and KnowledgeStore to provide a single entry point for processing
    enriched articles into persisted knowledge objects.

    Thread Safety:
        This class is stateless (all state is in dependencies) and thread-safe
        assuming the dependencies are thread-safe.

    Example:
        assembler = KnowledgeObjectAssembler(builder, validator, store)
        result = assembler.assemble(enriched_articles)
        logger.info(f"Created {result.created_count} new objects")
    """

    def __init__(
        self,
        builder: ObjectBuilder,
        validator: KnowledgeObjectValidator,
        store: KnowledgeStore,
    ) -> None:
        """Initialize the assembler with its dependencies.

        Args:
            builder: Service to construct KnowledgeObjects from EnrichedArticles.
            validator: Service to validate KnowledgeObject integrity.
            store: Storage backend implementing the KnowledgeStore protocol.
        """
        self._builder = builder
        self._validator = validator
        self._store = store

    def assemble(self, enriched_articles: list[EnrichedArticle]) -> AssemblyResult:
        """Run the full assembly pipeline on a batch of enriched articles.

        Pipeline stages:
        1. Build: Convert EnrichedArticles → KnowledgeObjects (skip failures).
        2. Validate: Check integrity of each built object.
        3. Persist: Save valid objects with idempotent semantics.

        Args:
            enriched_articles: Input batch from the extraction layer.

        Returns:
            AssemblyResult summarizing the pipeline outcome.
        """
        total_input = len(enriched_articles)
        logger.info("Assembly pipeline started with %d enriched articles", total_input)

        # Stage 1: Build
        built_objects = self._builder.build(enriched_articles)
        built_count = len(built_objects)
        logger.info("Build stage: %d objects constructed", built_count)

        # Stage 2: Validate
        valid_objects, invalid_objects = self._validator.validate_batch(built_objects)
        valid_count = len(valid_objects)
        invalid_count = len(invalid_objects)
        logger.info("Validation stage: %d valid, %d invalid", valid_count, invalid_count)

        # Stage 3: Persist (only valid objects)
        created_count = 0
        updated_count = 0
        if valid_objects:
            created_count = self._store.save_objects(valid_objects)
            updated_count = valid_count - created_count
            logger.info(
                "Persistence stage: %d created, %d updated",
                created_count,
                updated_count,
            )

        result = AssemblyResult(
            total_input=total_input,
            built_count=built_count,
            valid_count=valid_count,
            invalid_count=invalid_count,
            created_count=created_count,
            updated_count=updated_count,
        )

        logger.info(
            "Assembly pipeline completed: "
            "input=%d, built=%d, valid=%d, invalid=%d, created=%d, updated=%d",
            result.total_input,
            result.built_count,
            result.valid_count,
            result.invalid_count,
            result.created_count,
            result.updated_count,
        )

        return result
