"""Real SQLite prerequisites with deterministic local providers."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.config.importance import ImportanceConfig
from app.services.importance.scorer import ImportanceScorer
from app.services.intelligence.insight_generator import InsightGenerator
from app.services.intelligence.models import InsightBatch, InsightDraft
from app.services.repository.access_service import RepositoryAccessService
from app.services.trend.models import TrendRun
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from tests.fakes.analysis import make_analysis, make_knowledge
from tests.services.trend.test_evolution import snapshot

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
DAY = "2026-10-20"


def draft(**changes):
    """Build an evidence-backed connection using two existing knowledge IDs."""
    data = dict(
        insight_type="connection",
        title="Shared research direction",
        description="Two reports discuss related AI methods.",
        evidence_ids=["ko-0", "ko-1"],
        confidence=0.8,
    )
    data.update(changes)
    return InsightDraft(**data)


@pytest.fixture
def environment(tmp_path):
    store = SQLiteKnowledgeStore(tmp_path / "knowledge.db")
    access = RepositoryAccessService(store)
    for i in range(3):
        analysis = make_analysis(i, at=NOW)
        obj = make_knowledge(analysis).model_copy(
            update={
                "fetched_at": datetime(2026, 10, 20, 12, tzinfo=timezone.utc),
            }
        )
        store.save_objects([obj])
        access.save_content_analysis(analysis)
    trend = snapshot("2026-W42", 2).model_copy(update={"sample_knowledge_ids": ["ko-0", "ko-1"]})
    run = TrendRun(
        week="2026-W42",
        baseline_week="2026-W41",
        computed_at=trend.computed_at,
        current_items=3,
        baseline_items=1,
        snapshot_count=1,
        min_count=1,
    )
    access.save_trend_snapshots([trend], run=run)
    ImportanceScorer(access, None, ImportanceConfig(llm_top_n=0), clock=lambda: NOW).score_batch(
        [f"ko-{i}" for i in range(3)]
    )
    provider = MagicMock()
    provider.structured_chat.return_value = InsightBatch(insights=[draft()])
    generator = InsightGenerator(access, provider, clock=lambda: NOW)
    yield store, access, provider, generator
    store.close()
