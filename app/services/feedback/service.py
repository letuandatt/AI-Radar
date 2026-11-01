"""Single-reader feedback with deterministic scoring and no provider requests."""

import json
from collections import defaultdict
from typing import Any

from app.models.feedback import FeedbackRating, adjusted_importance
from app.services.feedback.models import (
    FeedbackRequest,
    TopicPreference,
    UserFeedback,
    UserPreferences,
)
from app.services.importance.models import ImportanceScore
from app.services.repository.access_service import RepositoryAccessService


class FeedbackService:
    """Use the repository gateway; async callers must offload these sync operations.

    Feedback changes only the chosen item's importance. Topic counts do not
    propagate scores to other items or rewrite existing digest snapshots.
    """

    def __init__(self, access: RepositoryAccessService) -> None:
        self._access = access

    def record_feedback(self, knowledge_id: str, request: FeedbackRequest) -> UserFeedback:
        """Persist the current choice and update any saved score in one transaction."""
        request = FeedbackRequest.model_validate(request.model_dump())
        return self._view(self._access.save_user_feedback(knowledge_id, request.rating))

    def get_feedback(self, knowledge_id: str) -> UserFeedback:
        """Read current feedback and its score from one repository snapshot."""
        return self._view(self._access.get_user_feedback(knowledge_id))

    def get_user_preferences(self) -> UserPreferences:
        """Aggregate only live rated items; duplicate topic labels count once per item."""
        rows = self._access.list_user_feedback_topics()
        counts: dict[str, dict[str, int]] = defaultdict(lambda: {"useful": 0, "not_useful": 0})
        for row in rows:
            topics = json.loads(row["metadata_json"]).get("topics", [])
            for topic in {str(value).strip().casefold() for value in topics} - {""}:
                counts[topic][row["rating"]] += 1
        ordered = sorted(counts, key=lambda topic: (-sum(counts[topic].values()), topic))[:50]
        return UserPreferences(
            rated_items=len(rows),
            topics=[TopicPreference(topic=topic, **counts[topic]) for topic in ordered],
        )

    @staticmethod
    def adjust_importance_score(base_score: float, rating: FeedbackRating | None) -> float:
        """Apply the explicit choice once; no model call and no cumulative boosting."""
        return adjusted_importance(base_score, rating)

    def _view(self, row: dict[str, Any]) -> UserFeedback:
        score = ImportanceScore.model_validate(row["score"]) if row["score"] else None
        base = (
            0.7 * score.rule_score + 0.3 * score.llm_score
            if score and score.llm_score is not None
            else score.rule_score
            if score
            else None
        )
        return UserFeedback(
            knowledge_id=row["knowledge_id"],
            rating=row["rating"],
            updated_at=row["updated_at"],
            base_score=base,
            adjusted_score=self.adjust_importance_score(base, row["rating"])
            if base is not None
            else None,
        )
