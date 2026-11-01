"""Deterministic priority and digest eligibility over saved importance scores."""

from collections.abc import Sequence
from urllib.parse import quote

from app.core.logger import get_logger
from app.services.importance.config import ImportanceConfig
from app.services.importance.models import PriorityEvaluation, PriorityLevel
from app.services.repository.access_service import RepositoryAccessService

logger = get_logger(__name__)


class PriorityEvaluator:
    """Read saved scores without rescoring, provider calls or database writes.

    Used by the local priority runner. Async callers must offload these synchronous
    methods with to_thread. Batch reads are per item, not a database-wide snapshot.
    Missing live items or scores raise LookupError; no partial list is returned.
    """

    def __init__(self, access_service: RepositoryAccessService, config: ImportanceConfig):
        self._access = access_service
        self._config = ImportanceConfig.model_validate(config.model_dump())

    def evaluate(self, knowledge_id: str) -> PriorityEvaluation:
        """Classify one saved final score and explain current digest eligibility."""
        if not isinstance(knowledge_id, str) or not knowledge_id.strip():
            raise ValueError("knowledge_id must be a nonblank string")

        saved = self._access.get_importance_score(knowledge_id)
        if saved is None:
            raise LookupError(f"No saved importance score for live item {knowledge_id!r}")

        item = self._access.get_knowledge_item(knowledge_id)
        if item is None:
            raise LookupError(f"Knowledge item {knowledge_id!r} is missing or deleted")

        if saved.knowledge_id != knowledge_id or item.id != knowledge_id:
            raise ValueError("Repository returned data for another knowledge_id")

        score = saved.final_score
        priority = PriorityLevel.from_score(score)
        label = f"{quote(item.source_type, safe='')}:{quote(item.source_name, safe='')}"
        category = (
            "github"
            if item.source_type == "github"
            else self._config.digest_source_categories.get(label)
        )

        threshold = None
        eligible = None
        reason = (
            f"Saved final_score={score!r} (computed_at={saved.computed_at.isoformat()}) "
            f"falls in {priority.value}; lower bound={priority.threshold:g}. "
        )
        if category is None:
            reason += f"Digest eligibility unknown: no category mapping for {label!r}."
        else:
            threshold = {
                "papers": self._config.threshold_papers,
                "github": self._config.threshold_github,
                "news": self._config.threshold_news,
            }[category]
            eligible = score >= threshold
            reason += (
                f"Current digest category={category}; score "
                f"{'meets' if eligible else 'is below'} threshold={threshold!r}."
            )

        return PriorityEvaluation(
            knowledge_id=knowledge_id,
            priority=priority,
            score=score,
            threshold_applied=priority.threshold,
            reason=reason,
            digest_category=category,
            digest_threshold=threshold,
            digest_eligible=eligible,
        )

    def evaluate_batch(self, knowledge_ids: Sequence[str]) -> list[PriorityEvaluation]:
        """Deduplicate IDs in input order; validate all IDs before reading data."""
        if isinstance(knowledge_ids, (str, bytes)) or not isinstance(knowledge_ids, Sequence):
            raise ValueError("knowledge_ids must be a sequence of nonblank strings")
        if any(not isinstance(value, str) or not value.strip() for value in knowledge_ids):
            raise ValueError("knowledge_ids must contain nonblank strings")

        ids = list(dict.fromkeys(knowledge_ids))
        if not ids:
            return []

        logger.info("Priority START: %d unique candidates", len(ids))
        results = [self.evaluate(knowledge_id) for knowledge_id in ids]
        logger.info("Priority DONE: %d evaluated", len(results))
        return results

    def filter_by_priority(
        self, knowledge_ids: Sequence[str], min_priority: PriorityLevel
    ) -> list[str]:
        """Keep priority >= minimum, in input order, independently of digest eligibility."""
        minimum = PriorityLevel(min_priority)
        return [
            row.knowledge_id
            for row in self.evaluate_batch(knowledge_ids)
            if row.priority.threshold >= minimum.threshold
        ]
