"""Deterministic daily selection over saved intelligence, analysis and importance."""

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.core.logger import get_logger
from app.models.knowledge_object import KnowledgeObject
from app.services.digest.config import Category, DigestConfig
from app.services.digest.models import DailyDigest, DigestItem, DigestSection, topic_groups
from app.services.importance.models import ImportanceScore
from app.services.intelligence.models import day_start
from app.services.repository.access_service import RepositoryAccessService

logger = get_logger(__name__)


class DailyDigestGenerator:
    """Sync API; async callers must offload the complete operation with to_thread.

    No upstream jobs or LLM calls. Ordinary generation returns the cached day;
    rebuild uses optimistic concurrency and preserves the old digest on failure.
    """

    def __init__(
        self,
        access_service: RepositoryAccessService,
        config: DigestConfig,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._access = access_service
        self._config = DigestConfig.model_validate(config.model_dump())
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def generate(self, date: str, *, rebuild: bool = False) -> DailyDigest:
        """Select up to five items per category and atomically cache the result."""
        started = self._clock()
        start = day_start(date)
        if started.utcoffset() is None or start > started:
            raise ValueError("Expected an aware clock and nonfuture digest date")
        logger.info("Digest START: date=%s, rebuild=%s", date, rebuild)
        cached = self._access.get_digest(date)
        if cached is not None and not rebuild:
            logger.info("Digest CACHE HIT: date=%s, items=%d", date, cached.total_items)
            return cached
        data = self._access.load_digest_inputs(date)
        document = data["document"]
        if document is None:
            raise LookupError(
                f"No refined intelligence for {date}; save the refined document first"
            )
        groups: dict[Category, list[DigestItem]] = {}
        eligible = unmapped = candidates = 0
        for row in data["candidates"]:
            item = KnowledgeObject.model_validate(row["item"])
            published = item.published_at
            fetched = item.fetched_at
            basis = published or fetched
            assumed = basis.utcoffset() is None
            when = basis.replace(tzinfo=timezone.utc) if assumed else basis
            if when > started:
                continue
            candidates += 1
            if row["score"] is None or row["themes"] is None:
                raise LookupError(f"Missing saved analysis or importance score: {item.id}")
            score = ImportanceScore.model_validate(row["score"])
            if score.knowledge_id != item.id:
                raise ValueError("Importance identity mismatch")
            category, threshold = self._config.selection(item.source_type, item.source_name)
            if threshold is None:
                unmapped += 1
                continue
            if score.final_score < threshold:
                continue
            eligible += 1
            topics = list(dict.fromkeys(t.strip() for t in row["themes"] if t.strip()))
            groups.setdefault(category, []).append(
                DigestItem(
                    knowledge_id=item.id,
                    title=item.title,
                    summary=item.metadata.summary,
                    source_type=item.source_type,
                    source_name=item.source_name,
                    source_url=item.source_url,
                    relevance_score=item.metadata.relevance_score,
                    published_at=when if published is not None else None,
                    fetched_at=fetched.replace(tzinfo=timezone.utc)
                    if fetched.utcoffset() is None
                    else fetched,
                    date_basis="published_at" if published is not None else "fetched_at",
                    assumed_utc=assumed,
                    importance_score=score.final_score,
                    score_computed_at=score.computed_at,
                    topics=topics,
                )
            )
        sections = [
            DigestSection(
                section_id=category,
                section_title=category.title(),
                category=category,
                items=sorted(items, key=lambda i: (-i.importance_score, i.knowledge_id))[
                    : self._config.max_items_per_section
                ],
            )
            for category, items in sorted(groups.items())
        ]
        digest = DailyDigest(
            digest_id=str(uuid4()),
            digest_date=date,
            started_at=started,
            generated_at=self._clock(),
            total_items=sum(len(s.items) for s in sections),
            candidate_count=candidates,
            eligible_count=eligible,
            unmapped_count=unmapped,
            sections=sections,
            topic_groups=topic_groups(sections),
            intelligence=document,
            config=self._config,
        )
        result = self._access.save_digest(
            digest,
            fingerprint=data["fingerprint"],
            rebuild=rebuild,
            expected_id=cached.digest_id if cached else None,
        )
        logger.info(
            "Digest DONE: date=%s, items=%d, eligible=%d, unmapped=%d",
            date,
            result.total_items,
            result.eligible_count,
            result.unmapped_count,
        )
        return result

    def get_digest(self, date: str) -> DailyDigest | None:
        """Read a saved snapshot without refreshing prerequisites."""
        return self._access.get_digest(date)

    def get_digest_history(self, limit: int = 30) -> list[str]:
        """Return available report dates newest first."""
        return self._access.get_digest_history(limit)
