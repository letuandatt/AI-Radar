"""Orchestrator service for the Knowledge Object assembly pipeline.

Coordinates the full flow: build → validate → persist.
This is the top-level entry point that the pipeline scheduler
will invoke to process enriched articles into stored knowledge.
"""

from dataclasses import dataclass, field
from typing import Literal

from app.core.logger import get_logger
from app.core.utils import compute_content_hash
from app.models.enriched_article import EnrichedArticle
from app.services.knowledge.object_builder import ObjectBuilder
from app.services.knowledge.object_validator import KnowledgeObjectValidator
from app.storage.knowledge.knowledge_store import KnowledgeStore

logger = get_logger(__name__)


@dataclass(frozen=True)
class PersistenceResult:
    """Item-level persistence outcome for one enriched article.

    Invariant (Wiring & Fix Plan A4): a checkpoint may only mark an article
    "stored" when its PersistenceResult.status is "created", "updated" or
    "skipped" — i.e. the KnowledgeObject really is in the repository.

    Attributes:
        url: Source URL of the article (for error reporting).
        content_hash: Pipeline checkpoint hash (url + title), used by the
            processing pipeline to update per-item state.
        status: created | updated | skipped | failed.
        error: Error description when status is "failed".
    """

    url: str
    content_hash: str
    status: Literal["created", "updated", "skipped", "failed"]
    error: str | None = None


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
        skipped_count: Number of objects skipped (idempotent).
        items: Per-article persistence outcomes (same order as input).
    """

    total_input: int
    built_count: int
    valid_count: int
    invalid_count: int
    created_count: int
    updated_count: int
    skipped_count: int
    items: list[PersistenceResult] = field(default_factory=list)


class KnowledgeObjectAssembler:
    """Orchestrates the full assembly pipeline: build → validate → persist.

    This service wires together ObjectBuilder, KnowledgeObjectValidator,
    and KnowledgeStore to provide a single entry point for processing
    enriched articles into persisted knowledge objects.

    Persistence is performed per object so that the outcome of every single
    article is observable (A4): aggregate counts alone cannot distinguish
    which items actually reached the store.

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

        Pipeline stages (per article):
        1. Build: Convert the EnrichedArticle → KnowledgeObject.
        2. Validate: Check integrity of the built object.
        3. Persist: Save the valid object with idempotent semantics.

        Articles whose extraction failed/skipped are reported as failed
        persistence results — they never silently disappear.

        Args:
            enriched_articles: Input batch from the extraction layer.

        Returns:
            AssemblyResult with aggregate counts and item-level outcomes.
        """
        total_input = len(enriched_articles)
        logger.info("Assembly pipeline started with %d enriched articles", total_input)

        items: list[PersistenceResult] = []
        built_count = 0
        valid_count = 0
        invalid_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for enriched_article in enriched_articles:
            article = enriched_article.article
            content_hash = compute_content_hash(article.url, article.title)

            # Articles whose extraction did not succeed never reach the store
            if (
                enriched_article.extraction_status != "success"
                or enriched_article.extraction is None
            ):
                items.append(
                    PersistenceResult(
                        url=article.url,
                        content_hash=content_hash,
                        status="failed",
                        error=f"extraction_status={enriched_article.extraction_status}",
                    )
                )
                continue

            try:
                built = self._builder.build([enriched_article])
                built_count += len(built)
                if not built:
                    items.append(
                        PersistenceResult(
                            url=article.url,
                            content_hash=content_hash,
                            status="failed",
                            error="build produced no KnowledgeObject",
                        )
                    )
                    continue

                valid_objects, invalid_objects = self._validator.validate_batch(built)
                valid_count += len(valid_objects)
                invalid_count += len(invalid_objects)
                if not valid_objects:
                    items.append(
                        PersistenceResult(
                            url=article.url,
                            content_hash=content_hash,
                            status="failed",
                            error="knowledge object failed validation",
                        )
                    )
                    continue

                save_result = self._store.save_objects(valid_objects)
                if save_result.created:
                    status: Literal["created", "updated", "skipped"] = "created"
                elif save_result.updated:
                    status = "updated"
                else:
                    status = "skipped"

                if status == "created":
                    created_count += 1
                elif status == "updated":
                    updated_count += 1
                else:
                    skipped_count += 1

                items.append(
                    PersistenceResult(
                        url=article.url,
                        content_hash=content_hash,
                        status=status,
                    )
                )
            except Exception as e:
                logger.error("Persistence failed for %s: %s", article.url, e)
                items.append(
                    PersistenceResult(
                        url=article.url,
                        content_hash=content_hash,
                        status="failed",
                        error=str(e),
                    )
                )

        logger.info(
            "Assembly pipeline completed: "
            "input=%d, built=%d, valid=%d, invalid=%d, "
            "created=%d, updated=%d, skipped=%d, failed=%d",
            total_input,
            built_count,
            valid_count,
            invalid_count,
            created_count,
            updated_count,
            skipped_count,
            total_input - created_count - updated_count - skipped_count,
        )

        return AssemblyResult(
            total_input=total_input,
            built_count=built_count,
            valid_count=valid_count,
            invalid_count=invalid_count,
            created_count=created_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            items=items,
        )
