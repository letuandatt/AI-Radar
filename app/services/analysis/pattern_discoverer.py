"""Temporal patterns from first-observed analyses, with evidence-grounded descriptions."""

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from statistics import fmean, pstdev
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.core.logger import get_logger
from app.integrations.llm.provider import LLMProvider
from app.prompts.builder import PromptBuilder
from app.prompts.loader import PromptLoader
from app.services.analysis.models import (
    DiscoveredPattern,
    ObservedKnowledgeItem,
    PatternDescriptions,
    PatternSnapshot,
)
from app.services.analysis.topics import source_labels, topic_signals
from app.services.repository.access_service import RepositoryAccessService

logger = get_logger(__name__)


class PatternDiscoverer:
    """Detect labels in code; use the shared LLM only to explain computed metrics.

    Every interval is (start, end]. Latest themes/entities are anchored to the
    first persisted analysis. This is not historical versioning of those labels.
    """

    def __init__(
        self,
        access_service: RepositoryAccessService,
        llm_provider: LLMProvider,
        prompt_loader: PromptLoader,
        batch_size: int = 10,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Inject shared dependencies; bound description requests by batch size."""
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        self._access = access_service
        self._llm = llm_provider
        self._template = prompt_loader.load("analytics/pattern_description")
        self._batch_size = batch_size
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def discover_patterns(self, time_window_days: int = 30) -> list[DiscoveredPattern]:
        """Detect, describe and atomically save a complete run; propagate failures.

        No LLM call or write occurs when there are no candidates. Same-day reruns
        update daily snapshots. Older completed runs cannot overwrite newer ones.
        This synchronous public API is not scheduled automatically. Database I/O
        and LLM requests block; async callers must offload the complete call with
        asyncio.to_thread, not execute it directly on the event loop.
        """
        days = time_window_days
        if isinstance(days, bool) or not isinstance(days, int) or days < 7:
            raise ValueError("time_window_days must be an integer >= 7")
        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        now = now.astimezone(timezone.utc)
        try:
            start = now - timedelta(days=max(2 * days, days + 7))
        except OverflowError as exc:
            raise ValueError("time_window_days exceeds datetime range") from exc
        logger.info("Pattern discovery: reading observations from %s to %s", start, now)
        items = self._access.list_pattern_items(start, now)
        candidates = self._detect(items, days, now)
        logger.info(
            "Pattern discovery: %d observations, %d candidates", len(items), len(candidates)
        )
        if not candidates:
            return []
        patterns: list[DiscoveredPattern] = []
        for offset in range(0, len(candidates), self._batch_size):
            batch = candidates[offset : offset + self._batch_size]
            logger.info(
                "Pattern descriptions: batch %d/%d (%d candidates)",
                offset // self._batch_size + 1,
                (len(candidates) + self._batch_size - 1) // self._batch_size,
                len(batch),
            )
            payload = [
                {key: item[key] for key in ("pattern_id", "pattern_type", "topic", "metrics")}
                for item in batch
            ]
            prompt = (
                PromptBuilder(self._template)
                .with_untrusted_data(json.dumps(payload, ensure_ascii=False, sort_keys=True))
                .build()
            )
            output = self._llm.structured_chat(prompt, PatternDescriptions)
            ids = [description.pattern_id for description in output.descriptions]
            expected = {item["pattern_id"] for item in batch}
            if len(ids) != len(set(ids)) or set(ids) != expected:
                raise ValueError("LLM descriptions must match every candidate ID exactly once")
            descriptions = {item.pattern_id: item.description for item in output.descriptions}
            patterns.extend(
                DiscoveredPattern(**item, description=descriptions[item["pattern_id"]])
                for item in batch
            )
        logger.info("Pattern discovery: saving %d patterns and daily snapshots", len(patterns))
        return self._access.save_discovered_patterns(patterns, observed_at=now)

    def get_pattern_history(self, pattern_id: str) -> list[PatternSnapshot]:
        """Read daily snapshots chronologically; unknown IDs return an empty list."""
        if not pattern_id.strip():
            raise ValueError("pattern_id must not be empty")
        return self._access.get_pattern_history(pattern_id)

    @staticmethod
    def _detect(
        items: list[ObservedKnowledgeItem], days: int, now: datetime
    ) -> list[dict[str, Any]]:
        buckets: dict[str, list[ObservedKnowledgeItem]] = {}
        for item in items:
            for topic in sorted(topic_signals(item)):
                buckets.setdefault(topic, []).append(item)
        cutoff = now - timedelta(days=days)
        recent_cutoff = now - timedelta(days=7)
        baseline_start = recent_cutoff - timedelta(days=days)
        previous_start = cutoff - timedelta(days=days)
        week_count = days // 7
        total_sources = len(
            source_labels([item for item in items if item.first_observed_at > cutoff])
        )
        candidates: list[dict[str, Any]] = []
        for topic, members in sorted(buckets.items()):
            current = [item for item in members if cutoff < item.first_observed_at <= now]
            previous = [
                item for item in members if previous_start < item.first_observed_at <= cutoff
            ]
            recent = [item for item in members if recent_cutoff < item.first_observed_at <= now]
            baseline = [
                item for item in members if baseline_start < item.first_observed_at <= recent_cutoff
            ]
            weekly: list[list[ObservedKnowledgeItem]] = [[] for _ in range(week_count)]
            for item in current:
                # Exact boundaries belong to the older bucket: (start, end].
                index = int((now - item.first_observed_at).total_seconds() // (7 * 86400))
                if index < week_count:
                    weekly[index].append(item)
            counts = [len(week) for week in weekly]
            mean = fmean(counts) if counts else 0.0
            cv = pstdev(counts) / mean if mean else None
            decline = (len(previous) - len(current)) / len(previous) if previous else None
            sources = source_labels(current)
            metrics = {
                "window_start": cutoff.isoformat(),
                "window_end": now.isoformat(),
                "time_basis": "first_observed_at",
                "current_count": len(current),
                "previous_count": len(previous),
                "recent_count": len(recent),
                "emerging_baseline_count": len(baseline),
                "weekly_counts_newest_first": counts,
                "weekly_window_days": week_count * 7,
                "weekly_excluded_count": len(current) - sum(counts),
                "cv": cv,
                "decline_ratio": decline,
                "current_source_count": len(sources),
                "total_sources": total_sources,
                "coverage_score": len(sources) / total_sources if total_sources else 0.0,
                "confidence_method": "mean_evidence_analysis_confidence",
            }
            matches = []
            if recent and not baseline:
                matches.append(("emerging", recent))
            if week_count >= 4 and cv is not None and cv < 0.3:
                matches.append(("recurring", [item for week in weekly for item in week]))
            if decline is not None and decline > 0.5:
                matches.append(("declining", previous + current))
            for kind, evidence in matches:
                identity = json.dumps([topic, kind, days], ensure_ascii=False)
                candidates.append(
                    {
                        "pattern_id": str(uuid5(NAMESPACE_URL, identity)),
                        "pattern_type": kind,
                        "topic": topic,
                        "time_window_days": days,
                        "first_detected": now,
                        "confidence": fmean(item.confidence for item in evidence),
                        "evidence_ids": sorted({item.knowledge_id for item in evidence}),
                        "metrics": metrics,
                    }
                )
        return candidates
