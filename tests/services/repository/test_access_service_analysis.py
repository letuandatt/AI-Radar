"""Tests for RepositoryAccessService analysis methods."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.services.analysis.models import (
    AnalysisEntities,
    ContentAnalysisResult,
)
from app.services.repository.access_service import RepositoryAccessService


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
