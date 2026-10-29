"""Generate a bounded, atomic daily insight report from persisted evidence."""

import json
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.core.logger import get_logger
from app.integrations.llm.provider import LLMProvider
from app.prompts.builder import PromptBuilder
from app.prompts.loader import PromptLoader
from app.services.intelligence.context import (
    displayed_trends,
    load_day,
    load_ranking,
    resolve_citation,
)
from app.services.intelligence.models import (
    Citation,
    Insight,
    InsightBatch,
    InsightRun,
    InsightType,
)
from app.services.repository.access_service import RepositoryAccessService

logger = get_logger(__name__)


class InsightGenerator:
    """Sync runner/API; async callers must offload the whole call with to_thread.

    At most one LLM call per day run, with 30 daily candidates, ten trend signals
    and ten saved patterns. Historical signal citations are separate from daily
    candidates. Failure preserves the prior report; a successful empty result
    replaces it. This validates provenance, not semantic truth of generated prose.
    """

    def __init__(
        self,
        access_service: RepositoryAccessService,
        llm_provider: LLMProvider,
        *,
        prompt_loader: PromptLoader | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._access = access_service
        self._provider = llm_provider
        self._prompts = prompt_loader or PromptLoader()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def generate_insights(self, date: str) -> list[Insight]:
        """Load existing prerequisites, validate every draft, then replace one day."""
        started = self._clock()
        logger.info("Insight generation START: date=%s", date)
        day = load_day(self._access, date, started)
        ranking = load_ranking(self._access, date, started)
        citations: dict[str, Citation] = {}
        evidence = []
        for row in day.candidates:
            citations[row.item.id] = resolve_citation(self._access, row.item.id)
            evidence.append(
                {
                    "knowledge_id": row.item.id,
                    "title": row.item.title[:300],
                    "summary": row.item.metadata.summary[:1000],
                    "analysis": {
                        "themes": [value[:100] for value in row.analysis.themes[:5]],
                        "key_claims": [value[:500] for value in row.analysis.key_claims[:3]],
                        "sentiment": row.analysis.sentiment,
                        "analyzed_at": row.analysis.analyzed_at.isoformat(),
                    },
                    "importance": row.score.final_score,
                    "score_computed_at": row.score.computed_at.isoformat(),
                }
            )
        signals = []
        support: dict[str, tuple[str, set[str]]] = {}
        for trend in displayed_trends(ranking)[:10]:
            ids = trend.sample_knowledge_ids
            support[trend.trend_id] = ("trend", set(ids))
            signals.append(
                {
                    "signal_id": trend.trend_id,
                    "kind": "trend",
                    "week": ranking.week,
                    "data": trend.model_dump(mode="json"),
                }
            )
        for pattern in day.patterns:
            # Keep prompt/output support bounded; never count duplicate IDs.
            ids = pattern.evidence_ids[:5]
            support[pattern.pattern_id] = ("pattern", set(ids))
            data = pattern.model_dump(mode="json")
            data["evidence_ids"] = ids
            data["description"] = pattern.description[:1000]
            signals.append({"signal_id": pattern.pattern_id, "kind": "pattern", "data": data})
        for _, signal_evidence in support.values():
            for identity in sorted(signal_evidence):
                if identity not in citations:
                    citations[identity] = resolve_citation(self._access, identity)
                    item = self._access.get_knowledge_item(identity)
                    if item is None:
                        raise LookupError(f"Missing signal evidence: {identity}")
                    evidence.append(
                        {
                            "knowledge_id": identity,
                            "title": item.title[:300],
                            "summary": str(item.metadata.get("summary", ""))[:1000],
                            "scope": "historical signal evidence",
                        }
                    )
        payload = {
            "report_date": date,
            "daily_candidates": len(day.candidates),
            "observed_daily_items": day.total_items,
            "trend_status": ranking.status,
            "evidence": evidence,
            "signals": signals,
        }
        drafts = InsightBatch(insights=[])
        if len(citations) >= 2:
            prompt = (
                PromptBuilder(self._prompts.load("intelligence/insight_generation"))
                .with_untrusted_data(json.dumps(payload, ensure_ascii=False, allow_nan=False))
                .build()
            )
            logger.info(
                "Insight generation LLM: daily=%d, evidence=%d, signals=%d",
                len(day.candidates),
                len(citations),
                len(signals),
            )
            output = self._provider.structured_chat(prompt, InsightBatch)
            drafts = InsightBatch.model_validate(output.model_dump())
        generated = self._clock()
        results = []
        for draft in drafts.insights:
            if not set(draft.evidence_ids) <= citations.keys():
                raise ValueError("LLM selected unknown evidence IDs")
            for signal_id in draft.signal_ids:
                if signal_id not in support:
                    raise ValueError("LLM selected an unknown signal ID")
                kind, signal_evidence = support[signal_id]
                if draft.insight_type in {"trend", "pattern"} and kind != draft.insight_type:
                    raise ValueError("Insight type does not match its persisted signal")
                if len(signal_evidence.intersection(draft.evidence_ids)) < 2:
                    raise ValueError("Each signal needs two of its own evidence IDs")
            results.append(
                Insight(
                    **draft.model_dump(),
                    insight_id=str(uuid4()),
                    report_date=date,
                    citations=[citations[key] for key in draft.evidence_ids],
                    generated_at=generated,
                )
            )
        run = InsightRun(
            report_date=date,
            started_at=started,
            generated_at=generated,
            candidate_count=len(day.candidates),
            insight_count=len(results),
            trend_week=ranking.week,
        )
        self._access.save_insights(results, run=run)
        logger.info("Insight generation DONE: date=%s, insights=%d", date, len(results))
        return results

    def get_insights_by_type(self, type: InsightType, limit: int = 5) -> list[Insight]:
        """Read the newest successful report day, including a successful empty day."""
        if type not in {"trend", "pattern", "connection", "warning"}:
            raise ValueError("Unknown insight type")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ValueError("limit must be between 1 and 10")
        _, rows = self._access.read_insight_report()
        return [row for row in rows if row.insight_type == type][:limit]
