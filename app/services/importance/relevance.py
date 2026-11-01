"""Assess topic fit using saved extraction relevance and retrieved neighbors."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from math import isfinite

from app.core.logger import get_logger
from app.services.importance.models import RelevanceAssessment
from app.services.repository.access_service import RepositoryAccessService
from app.services.repository.query_models import KnowledgeQuery, PaginationMode
from app.services.retrieval.retrieval_service import RetrievalService

logger = get_logger(__name__)


class RelevanceAssessor:
    """Read-only service used by the local relevance runner.

    No LLM, embeddings, score updates or deletions are performed. Async callers
    must offload the entire synchronous call with to_thread. Retrieval failures
    propagate; they never become zero relevance or insufficient-context results.
    """

    def __init__(
        self,
        access_service: RepositoryAccessService,
        retrieval_service: RetrievalService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._access = access_service
        self._retrieval = retrieval_service
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _topics(values: list[str]) -> set[str]:
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError("Topics must be a list of strings")
        return {
            normalized for value in values if (normalized := " ".join(value.split()).casefold())
        }

    def assess(self, knowledge_id: str) -> RelevanceAssessment:
        """Combine saved base relevance (70%) with observed topic overlap (30%)."""
        if not isinstance(knowledge_id, str) or not knowledge_id.strip():
            raise ValueError("knowledge_id must be a nonblank string")

        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("Assessment clock must be timezone-aware")

        saved = self._access.get_importance_score(knowledge_id)
        if saved is None:
            raise LookupError(f"No saved importance score for live item {knowledge_id!r}")

        item = self._access.get_knowledge_item(knowledge_id)
        if item is None:
            raise LookupError(f"Knowledge item {knowledge_id!r} is missing or deleted")

        if saved.knowledge_id != knowledge_id or item.id != knowledge_id:
            raise ValueError("Repository returned data for another knowledge_id")

        if saved.component_status["relevance_score"] != "observed":
            raise ValueError("Saved extraction relevance must be observed")

        base = saved.components["relevance_score"]
        topics = self._topics(item.metadata.get("topics", []))
        response = self._retrieval.get_related_items(knowledge_id, top_k=5)
        related: list[str] = []
        overlaps: list[float] = []

        for result in response.results:
            key = result.knowledge_id
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Retrieval returned a blank or invalid knowledge_id")

            if key == knowledge_id or key in related:
                continue

            related.append(key)
            neighbor_topics = self._topics(result.topics)
            if topics and neighbor_topics:
                overlaps.append(len(topics & neighbor_topics) / len(topics | neighbor_topics))

            if len(related) == 5:
                break

        consistency = sum(overlaps) / len(overlaps) if overlaps else None
        reason = (
            f"Base extraction relevance={base!r} from score computed_at="
            f"{saved.computed_at.isoformat()}; {len(related)} unique neighbors. "
        )
        if consistency is not None:
            reason += (
                f"Mean topic Jaccard={consistency!r} over {len(overlaps)} usable neighbors; "
                "relevance=0.7*base+0.3*consistency. Retrieval scores are not used."
            )
        else:
            reason += (
                "No topics on the assessed item; " if not topics else "No usable neighbor topics; "
            )
            reason += "base relevance retained; excluded from irrelevant-item selection."
        return RelevanceAssessment(
            knowledge_id=knowledge_id,
            assessed_at=now.astimezone(timezone.utc),
            relevance_score=base if consistency is None else 0.7 * base + 0.3 * consistency,
            related_items=related,
            topic_consistency=consistency,
            base_relevance=base,
            status="insufficient_context" if consistency is None else "assessed",
            reason=reason,
        )

    def assess_batch(self, knowledge_ids: Sequence[str]) -> list[RelevanceAssessment]:
        """Validate first, deduplicate in input order, and fail without a partial return."""
        if isinstance(knowledge_ids, (str, bytes)) or not isinstance(knowledge_ids, Sequence):
            raise ValueError("knowledge_ids must be a sequence of nonblank strings")
        if any(not isinstance(key, str) or not key.strip() for key in knowledge_ids):
            raise ValueError("knowledge_ids must contain nonblank strings")
        ids = list(dict.fromkeys(knowledge_ids))
        results = []
        for index, key in enumerate(ids, start=1):
            logger.info("Relevance %d/%d: %s", index, len(ids), key)
            results.append(self.assess(key))
        return results

    def find_irrelevant_items(self, threshold: float = 0.3) -> list[str]:
        """Scan all live items, returning assessed scores strictly below threshold.

        Run against a quiescent repository: offset pages are not a shared snapshot.
        Count changes, duplicate IDs and incomplete pages fail explicitly. Missing
        scores or retrieval errors abort the scan; nothing is deleted or persisted.
        """
        if isinstance(threshold, bool) or not isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("threshold must be finite and between 0 and 1")
        offset = 0
        expected_total: int | None = None
        seen: set[str] = set()
        selected: list[str] = []
        while True:
            page = self._access.search_knowledge(
                KnowledgeQuery(pagination_mode=PaginationMode.PAGE, limit=100, offset=offset)
            )
            if expected_total is None:
                expected_total = page.total
            if page.total is None or page.total != expected_total:
                raise RuntimeError("Repository count changed or is unavailable during scan")
            ids = [item.id for item in page.items]
            if len(ids) != len(set(ids)) or seen.intersection(ids):
                raise RuntimeError("Repository pagination returned duplicate IDs")
            if not ids and page.page_info.has_next:
                raise RuntimeError("Repository pagination did not advance")
            rows = self.assess_batch(ids)
            selected.extend(
                row.knowledge_id
                for row in rows
                if row.status == "assessed" and row.relevance_score < threshold
            )
            seen.update(ids)
            offset += len(ids)
            logger.info(
                "Relevance scan: %d/%d read, %d candidates; page insufficient_context=%d",
                offset,
                expected_total,
                len(selected),
                sum(row.status == "insufficient_context" for row in rows),
            )
            if not page.page_info.has_next:
                if len(seen) != expected_total:
                    raise RuntimeError("Repository scan ended before all live items were read")
                return selected
