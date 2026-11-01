"""Tests for RepositoryAccessService analysis methods."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.analysis.models import (
    AnalysisEntities,
    ContentAnalysisResult,
)
from app.services.repository.access_service import RepositoryAccessService
from tests.fakes.analysis import NOW, make_analysis


@pytest.fixture
def mock_sqlite_store():
    """Provide a mock SQLiteKnowledgeStore."""
    store = MagicMock()
    store.query_unanalyzed.return_value = []
    store.save_analysis.return_value = None
    return store


@pytest.fixture
def access_service(mock_sqlite_store):
    """Provide a RepositoryAccessService with mocked store."""
    return RepositoryAccessService(mock_sqlite_store)


class TestListUnanalyzedItems:
    """Tests for list_unanalyzed_items()."""

    def test_delegates_to_store(self, access_service, mock_sqlite_store) -> None:
        """list_unanalyzed_items delegates to sqlite_store.query_unanalyzed."""
        access_service.list_unanalyzed_items(limit=20)
        mock_sqlite_store.query_unanalyzed.assert_called_once_with(20)

    def test_default_limit(self, access_service, mock_sqlite_store) -> None:
        """Default limit is 50."""
        access_service.list_unanalyzed_items()
        mock_sqlite_store.query_unanalyzed.assert_called_once_with(50)


class TestSaveContentAnalysis:
    """Tests for save_content_analysis()."""

    def test_saves_analysis(self, access_service, mock_sqlite_store) -> None:
        """save_content_analysis persists result to store."""
        result = ContentAnalysisResult(
            knowledge_id="ko-123",
            analyzed_at=datetime.now(timezone.utc),
            themes=["RAG", "Retrieval"],
            entities=AnalysisEntities(
                models=["GPT-4"],
                companies=["OpenAI"],
                people=[],
            ),
            sentiment="positive",
            key_claims=["RAG improves accuracy"],
            technical_depth="intermediate",
            confidence=0.87,
        )

        access_service.save_content_analysis(result)

        mock_sqlite_store.save_analysis.assert_called_once()

        # Verify arguments
        call_kwargs = mock_sqlite_store.save_analysis.call_args[1]
        assert call_kwargs["knowledge_id"] == "ko-123"
        assert call_kwargs["sentiment"] == "positive"
        assert call_kwargs["technical_depth"] == "intermediate"
        assert call_kwargs["confidence"] == 0.87
        assert '"RAG"' in call_kwargs["themes_json"]
        assert '"GPT-4"' in call_kwargs["entities_json"]

    def test_generates_unique_analysis_id(self, access_service, mock_sqlite_store) -> None:
        """Each save generates a unique analysis_id."""
        result = ContentAnalysisResult(
            knowledge_id="ko-123",
            analyzed_at=datetime.now(timezone.utc),
            themes=["AI"],
            entities=AnalysisEntities(),
            sentiment="neutral",
            key_claims=["Claim"],
            technical_depth="beginner",
            confidence=0.5,
        )

        access_service.save_content_analysis(result)
        access_service.save_content_analysis(result)

        calls = mock_sqlite_store.save_analysis.call_args_list
        id1 = calls[0][1]["analysis_id"]
        id2 = calls[1][1]["analysis_id"]
        assert id1 != id2


def test_window_mapping_uses_one_utc_clock_read(access_service, mock_sqlite_store, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr("app.services.repository.access_service.datetime", FrozenDateTime)
    item = make_analysis()
    row = item.model_dump(mode="json")
    for key in ("themes", "entities", "key_claims"):
        row[f"{key}_json"] = json.dumps(row.pop(key))
    mock_sqlite_store.query_analyses_in_window.return_value = [row]
    assert access_service.list_items_in_window(7) == [item]
    mock_sqlite_store.query_analyses_in_window.assert_called_once_with(
        (NOW - timedelta(days=7)).isoformat(), NOW.isoformat()
    )


@pytest.mark.parametrize("days", [0, -1, True, 1.5, 10**10])
def test_invalid_window_is_rejected_before_query(access_service, mock_sqlite_store, days):
    with pytest.raises(ValueError):
        access_service.list_items_in_window(days)
    mock_sqlite_store.query_analyses_in_window.assert_not_called()


def test_empty_groups_still_replace_selected_window(access_service, mock_sqlite_store):
    access_service.save_cross_source_groups([], time_window_days=30)
    mock_sqlite_store.replace_cross_source_groups.assert_called_once_with(30, [])


@pytest.mark.parametrize("days", [0, -1, True, 1.5])
def test_invalid_snapshot_window_is_rejected(access_service, mock_sqlite_store, days):
    with pytest.raises(ValueError):
        access_service.save_cross_source_groups([], time_window_days=days)
    mock_sqlite_store.replace_cross_source_groups.assert_not_called()
