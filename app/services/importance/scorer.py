"""Deterministic six-signal scoring with bounded, shared-chain LLM refinement."""

import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from math import log1p
from urllib.parse import quote

from app.core.logger import get_logger
from app.integrations.llm.provider import LLMProvider
from app.models.knowledge_object import KnowledgeObject
from app.prompts.builder import PromptBuilder
from app.prompts.loader import PromptLoader
from app.services.analysis.models import AnalyzedKnowledgeItem
from app.services.analysis.topics import topic_signals
from app.services.importance.config import ImportanceConfig
from app.services.importance.models import (
    ImportanceScore,
    LLMImportanceScore,
    ScoreContext,
    SignalStatus,
)
from app.services.repository.access_service import RepositoryAccessService
from app.services.trend.models import week_label, week_start

logger = get_logger(__name__)


class ImportanceScorer:
    """Score a batch atomically; async callers must offload the entire sync call.

    This public API is called by the local scoring runner. Startup never scores
    items. A failed refinement leaves all previous saved scores unchanged, though
    provider requests already made may have consumed budget. No implicit cache.
    """

    def __init__(
        self,
        access_service: RepositoryAccessService,
        llm_provider: LLMProvider | None,
        config: ImportanceConfig | None = None,
        *,
        prompt_loader: PromptLoader | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._access = access_service
        self._provider = llm_provider
        self._config = ImportanceConfig.model_validate((config or ImportanceConfig()).model_dump())
        if self._config.llm_top_n and llm_provider is None:
            raise ValueError("Hybrid scoring requires a provider; use llm_top_n=0 for rule-only")
        self._template = (
            (prompt_loader or PromptLoader()).load("importance/score_refinement")
            if self._config.llm_top_n
            else ""
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def score_batch(self, knowledge_ids: Sequence[str]) -> list[ImportanceScore]:
        """Validate all IDs, score unique items, refine top N, then save once.

        Return final-score descending with ID tie-breaking. Missing/deleted IDs
        fail before LLM calls. Duplicate input IDs are scored only once.
        """
        if isinstance(knowledge_ids, (str, bytes)) or any(
            not isinstance(value, str) or not value.strip() for value in knowledge_ids
        ):
            raise ValueError("knowledge_ids must be a sequence of nonempty strings")

        ids = sorted(set(knowledge_ids))
        if not ids:
            return []

        now = self._clock()
        if now.utcoffset() is None:
            raise ValueError("clock must be timezone-aware")

        now = now.astimezone(timezone.utc)
        start = now - timedelta(days=self._config.cross_source_days)
        week = week_label(week_start(week_label(now)) - timedelta(days=7))
        logger.info("Importance START: %d candidates, top_n=%d", len(ids), self._config.llm_top_n)

        inputs = self._access.load_importance_inputs(ids, start, now, week)
        objects = {obj.id: obj for obj in inputs.objects}
        if set(objects) != set(ids):
            raise LookupError(f"Missing live knowledge IDs: {sorted(set(ids) - set(objects))}")

        analyses = {row.knowledge_id: row for row in inputs.analyses if row.analyzed_at <= now}
        window = [row for row in inputs.analyses if start <= row.analyzed_at <= now]
        sources: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for row in window:
            for signal in topic_signals(row):
                sources[signal].add((row.source_type, row.source_name))

        trend_map = {row.name: row for row in inputs.trends if row.type == "entity"}
        scores = []
        for identity in ids:
            obj, analysis = objects[identity], analyses.get(identity)
            signals = topic_signals(analysis) if analysis is not None else set()
            in_window = analysis is not None and start <= analysis.analyzed_at <= now
            source_count = (
                max((len(sources[key]) for key in signals), default=0) if in_window else 0
            )

            entities = sorted(key for key in signals if not key.startswith("theme:"))
            matches = [key for key in entities if key in trend_map]
            entity_ready = inputs.trend_run is not None and inputs.trend_run.current_items > 0
            label = f"{quote(obj.source_type, safe='')}:{quote(obj.source_name, safe='')}"
            published = obj.published_at
            assumed = published is not None and published.utcoffset() is None
            if published is not None and assumed:
                published = published.replace(tzinfo=timezone.utc)
            if published is not None:
                published = published.astimezone(timezone.utc)

            stars = obj.github_stars if obj.source_type == "github" else None
            components = {
                "relevance_score": obj.metadata.relevance_score,
                "freshness": (
                    min(
                        1.0,
                        max(
                            0.0,
                            1
                            - (now - published).total_seconds()
                            / (86400 * self._config.max_age_days),
                        ),
                    )
                    if published is not None
                    else 0.0
                ),
                "source_authority": self._config.source_authorities.get(
                    label, self._config.default_authority
                ),
                "github_stars": min(1.0, log1p(stars) / log1p(self._config.stars_cap))
                if stars is not None
                else 0.0,
                "cross_source_mentions": min(
                    1.0, max(0, source_count - 1) / (self._config.source_cap - 1)
                ),
                "entity_importance": max(
                    (trend_map[key].normalized_count for key in matches), default=0.0
                )
                if entity_ready
                else 0.0,
            }
            status: dict[str, SignalStatus] = {
                "relevance_score": "observed",
                "freshness": "observed" if published is not None else "missing",
                "source_authority": "observed"
                if label in self._config.source_authorities
                else "defaulted",
                "github_stars": "not_applicable"
                if obj.source_type != "github"
                else "missing"
                if stars is None
                else "observed",
                "cross_source_mentions": "observed" if in_window else "missing",
                "entity_importance": "missing"
                if analysis is None
                else "not_applicable"
                if not entities
                else "observed"
                if entity_ready
                else "missing",
            }
            rule = min(
                1.0, sum(self._config.weights[key] * value for key, value in components.items())
            )
            scores.append(
                ImportanceScore(
                    knowledge_id=identity,
                    computed_at=now,
                    rule_score=rule,
                    final_score=rule,
                    components=components,
                    component_status=status,
                    config=self._config,
                    context=ScoreContext(
                        window_start=start,
                        window_end=now,
                        trend_week=week,
                        trend_computed_at=inputs.trend_run.computed_at
                        if inputs.trend_run
                        else None,
                        observed_items=len(window),
                        matched_source_count=source_count,
                        entity_matches=matches,
                        published_at=published,
                        publication_assumed_utc=assumed,
                        publication_in_future=published is not None and published > now,
                        github_stars=stars,
                        source_label=label,
                    ),
                )
            )
        scores.sort(key=lambda score: (-score.rule_score, score.knowledge_id))
        selected = min(self._config.llm_top_n, len(scores))
        for index in range(selected):
            current = scores[index]
            logger.info(
                "Importance refinement %d/%d: %s", index + 1, selected, current.knowledge_id
            )

            assert self._provider is not None
            output = self._provider.structured_chat(
                self._prompt(
                    objects[current.knowledge_id], analyses.get(current.knowledge_id), current
                ),
                LLMImportanceScore,
            )

            output = LLMImportanceScore.model_validate(output.model_dump())
            if output.knowledge_id != current.knowledge_id:
                raise ValueError("LLM refinement returned another knowledge_id")

            scores[index] = ImportanceScore.model_validate(
                {
                    **current.model_dump(),
                    "llm_adjusted": True,
                    "llm_score": output.score,
                    "llm_reason": output.reason,
                    "final_score": 0.7 * current.rule_score + 0.3 * output.score,
                }
            )
        scores.sort(key=lambda score: (-score.final_score, score.knowledge_id))
        self._access.save_importance_scores(scores)
        logger.info("Importance DONE: %d saved, %d refined", len(scores), selected)
        return scores

    def get_score(self, knowledge_id: str) -> ImportanceScore | None:
        """Return the saved score for a live item; never recompute implicitly."""
        return self._access.get_importance_score(knowledge_id)

    def _prompt(
        self, obj: KnowledgeObject, analysis: AnalyzedKnowledgeItem | None, score: ImportanceScore
    ) -> str:
        payload = {
            "knowledge_id": obj.id,
            "title": obj.title[:500],
            "summary": obj.metadata.summary[:2000],
            "content_excerpt": obj.content_text[:6000],
            "analysis": analysis.model_dump(mode="json") if analysis else None,
            "rule_score": score.rule_score,
            "components": score.components,
            "component_status": score.component_status,
            "context": score.context.model_dump(mode="json"),
        }
        return (
            PromptBuilder(self._template)
            .with_untrusted_data(json.dumps(payload, ensure_ascii=False, allow_nan=False))
            .build()
        )
