"""Deterministic cross-source analysis over persisted content analyses."""

import json
from uuid import NAMESPACE_URL, uuid5

from app.integrations.llm.provider import LLMProvider
from app.services.analysis.models import (
    AnalyzedKnowledgeItem,
    CrossSourceCoverage,
    CrossSourceGroup,
)
from app.services.analysis.topics import normalize_topic, source_labels, topic_signals
from app.services.repository.access_service import RepositoryAccessService


class CrossSourceAnalyzer:
    """Group exact normalized themes/entities without additional LLM calls.

    A theme and an entity with the same text remain distinct topics. Groups
    may overlap; sharing one signal never merges unrelated signals transitively.
    """

    def __init__(
        self,
        access_service: RepositoryAccessService,
        llm_provider: LLMProvider,
        max_groups: int = 20,
    ) -> None:
        """Use the shared provider contract and configure the returned group limit."""
        if isinstance(max_groups, bool) or not isinstance(max_groups, int) or max_groups <= 0:
            raise ValueError("max_groups must be a positive integer")
        self._access_service = access_service
        self._llm_provider = llm_provider
        self._max_groups = max_groups

    def find_groups(self, time_window_days: int = 7) -> list[CrossSourceGroup]:
        """Replace the window's persisted groups and return the highest-ranked N.

        Persistence includes all qualifying groups, even those outside top N.
        An empty result clears the previous snapshot for this window only.
        """
        buckets, total_sources = self._load_topics(time_window_days)
        groups = []
        for topic, members in buckets.items():
            coverage = self._coverage(topic, members, total_sources, time_window_days)
            if coverage.source_count < 2:
                continue
            identity = json.dumps([time_window_days, topic], ensure_ascii=False)
            groups.append(
                CrossSourceGroup(
                    group_id=str(uuid5(NAMESPACE_URL, identity)),
                    topic=topic,
                    knowledge_ids=coverage.knowledge_ids,
                    source_count=coverage.source_count,
                    sources=coverage.sources,
                    first_seen=min(item.analyzed_at for item in members),
                    last_seen=max(item.analyzed_at for item in members),
                    coverage_score=coverage.coverage_score,
                )
            )
        groups.sort(
            key=lambda group: (-group.coverage_score, -len(group.knowledge_ids), group.topic)
        )
        self._access_service.save_cross_source_groups(groups, time_window_days=time_window_days)
        return groups[: self._max_groups]

    def find_coverage(self, topic: str, time_window_days: int = 7) -> CrossSourceCoverage:
        """Read coverage without persistence or top-N filtering.

        Bare text means a theme ("RAG" -> "theme:rag"). Use an explicit
        namespace for entities, for example "models:GPT-4".
        """
        normalized = normalize_topic(topic)
        if not normalized:
            raise ValueError("topic must not be empty")
        prefix, separator, value = normalized.partition(":")
        if separator and prefix in {"theme", "models", "companies", "people"}:
            value = value.strip()
            if not value:
                raise ValueError("topic value must not be empty")
            key = f"{prefix}:{value}"
        else:
            key = f"theme:{normalized}"
        buckets, total_sources = self._load_topics(time_window_days)
        return self._coverage(key, buckets.get(key, []), total_sources, time_window_days)

    def _load_topics(self, days: int) -> tuple[dict[str, list[AnalyzedKnowledgeItem]], int]:
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise ValueError("time_window_days must be a positive integer")
        items = self._access_service.list_items_in_window(days)
        buckets: dict[str, list[AnalyzedKnowledgeItem]] = {}
        sources = set()
        for item in items:
            sources.add((item.source_type, item.source_name))
            for signal in sorted(topic_signals(item)):
                buckets.setdefault(signal, []).append(item)
        return buckets, len(sources)

    @staticmethod
    def _coverage(
        topic: str,
        members: list[AnalyzedKnowledgeItem],
        total_sources: int,
        days: int,
    ) -> CrossSourceCoverage:
        sources = source_labels(members)
        ids = sorted({item.knowledge_id for item in members})
        return CrossSourceCoverage(
            topic=topic,
            time_window_days=days,
            knowledge_ids=ids,
            sources=sources,
            article_count=len(ids),
            source_count=len(sources),
            total_sources=total_sources,
            coverage_score=len(sources) / total_sources if total_sources else 0.0,
            first_seen=min((item.analyzed_at for item in members), default=None),
            last_seen=max((item.analyzed_at for item in members), default=None),
        )
