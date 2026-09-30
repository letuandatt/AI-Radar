"""Tests for ContentAnalyzer service."""

from unittest.mock import MagicMock

import pytest

from app.models.knowledge_object import KnowledgeObject
from app.prompts.loader import PromptLoader
from app.services.analysis.content_analyzer import ContentAnalyzer
from app.services.analysis.models import (
    AnalysisEntities,
    ContentAnalysisOutput,
    ContentAnalysisResult,
)
from app.services.repository.query_models import KnowledgeDetailResponse


@pytest.fixture
def mock_access_service():
    """Provide a mock RepositoryAccessService."""
    service = MagicMock()
    service.list_unanalyzed_items.return_value = []
    service.save_content_analysis.return_value = None
    return service


@pytest.fixture
def mock_llm_provider():
    """Provide a mock LLMProvider."""
    provider = MagicMock()
    provider.get_provider_name.return_value = "ollama"
    provider.get_model_name.return_value = "qwen3:4b"
    return provider


@pytest.fixture
def mock_prompt_loader():
    """Provide a mock PromptLoader."""
    loader = MagicMock()
    loader.load.return_value = "Analyze: {untrusted_data}"
    return loader


@pytest.fixture
def analyzer(mock_access_service, mock_llm_provider, mock_prompt_loader):
    """Provide a ContentAnalyzer with mocked dependencies."""
    return ContentAnalyzer(
        access_service=mock_access_service,
        llm_provider=mock_llm_provider,
        prompt_loader=mock_prompt_loader,
        max_concurrent=2,
    )


@pytest.fixture
def sample_knowledge_object():
    """Provide a sample KnowledgeObject."""
    return KnowledgeObject(
        id="ko-test-123",
        title="Test Article About RAG",
        content_text="Retrieval Augmented Generation improves accuracy.",
        source_type="rss",
        source_name="techcrunch",
        source_url="https://example.com/article",
        content_hash="abc123",
        fetched_at="2023-01-01T00:00:00Z",
        published_at="2023-01-01T00:00:00Z",
        external_id="ext_123",
        metadata={
            "category": "technology",
            "summary": "This article discusses the benefits of RAG.",
            "topics": ["AI", "Retrieval"],
            "entities": ["GPT-4", "OpenAI"],
            "relevance_score": 0.85,
        },
    )


@pytest.mark.asyncio
async def test_analyze_works_with_real_detail_response():
    """analyze() phải hoạt động với KnowledgeDetailResponse THẬT (không mock loader)."""
    analyzer = ContentAnalyzer(
        access_service=MagicMock(),
        llm_provider=MagicMock(),
        prompt_loader=PromptLoader(),
    )
    item = KnowledgeDetailResponse(
        id="abc-123",
        title="Test article",
        source_type="rss",
        source_name="blog",
        content_text="Some AI news content",
        content_hash="hash",
    )
    analyzer._access_service.get_knowledge_item.return_value = item
    analyzer._llm_provider.structured_chat.return_value = ContentAnalysisOutput(
        themes=["t"],
        entities={},
        sentiment="neutral",
        key_claims=["c"],
        technical_depth="beginner",
        confidence=0.9,
    )

    result = await analyzer.analyze("abc-123")
    assert result.knowledge_id == "abc-123"


class TestAnalyze:
    """Tests for ContentAnalyzer.analyze()."""

    @pytest.mark.asyncio
    async def test_analyze_success(
        self, analyzer, mock_access_service, mock_llm_provider, sample_knowledge_object
    ) -> None:
        """Successful analysis returns ContentAnalysisResult."""
        # Setup
        detail_response = MagicMock()
        detail_response.knowledge_object = sample_knowledge_object
        mock_access_service.get_knowledge_item.return_value = detail_response

        llm_output = ContentAnalysisOutput(
            themes=["RAG", "Retrieval"],
            entities=AnalysisEntities(models=["GPT-4"]),
            sentiment="positive",
            key_claims=["RAG improves accuracy"],
            technical_depth="intermediate",
            confidence=0.85,
        )
        mock_llm_provider.structured_chat.return_value = llm_output

        # Execute
        result = await analyzer.analyze("ko-test-123")

        # Verify
        assert isinstance(result, ContentAnalysisResult)
        assert result.knowledge_id == "ko-test-123"
        assert result.themes == ["RAG", "Retrieval"]
        assert result.sentiment == "positive"
        mock_access_service.save_content_analysis.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_not_found(self, analyzer, mock_access_service) -> None:
        """Analysis of non-existent item raises ValueError."""
        mock_access_service.get_knowledge_item.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await analyzer.analyze("nonexistent-id")

    @pytest.mark.asyncio
    async def test_analyze_empty_themes_rejected(
        self, analyzer, mock_access_service, mock_llm_provider, sample_knowledge_object
    ) -> None:
        """LLM output with empty themes is rejected."""
        detail_response = MagicMock()
        detail_response.knowledge_object = sample_knowledge_object
        mock_access_service.get_knowledge_item.return_value = detail_response

        llm_output = ContentAnalysisOutput(
            themes=[],
            entities=AnalysisEntities(),
            sentiment="neutral",
            key_claims=["Claim"],
            technical_depth="beginner",
            confidence=0.5,
        )
        mock_llm_provider.structured_chat.return_value = llm_output

        with pytest.raises(ValueError, match="empty themes"):
            await analyzer.analyze("ko-test-123")


class TestAnalyzeBatch:
    """Tests for ContentAnalyzer.analyze_batch()."""

    @pytest.mark.asyncio
    async def test_batch_empty(self, analyzer, mock_access_service) -> None:
        """Empty batch returns empty list."""
        mock_access_service.list_unanalyzed_items.return_value = []

        results = await analyzer.analyze_batch(limit=10)

        assert results == []

    @pytest.mark.asyncio
    async def test_batch_partial_failure(
        self, analyzer, mock_access_service, mock_llm_provider
    ) -> None:
        """Batch continues after individual failures."""
        # Setup: 2 items, first succeeds, second fails
        item1 = MagicMock()
        item1.id = "ko-1"
        item2 = MagicMock()
        item2.id = "ko-2"
        mock_access_service.list_unanalyzed_items.return_value = [item1, item2]

        # First item: success
        detail1 = MagicMock()
        ko1 = MagicMock()
        ko1.title = "Article 1"
        ko1.content_text = "Content 1"
        detail1.knowledge_object = ko1

        # Second item: not found (will raise ValueError)
        def get_item_side_effect(item_id):
            if item_id == "ko-1":
                return detail1
            return None

        mock_access_service.get_knowledge_item.side_effect = get_item_side_effect

        llm_output = ContentAnalysisOutput(
            themes=["AI"],
            entities=AnalysisEntities(),
            sentiment="positive",
            key_claims=["Claim"],
            technical_depth="beginner",
            confidence=0.8,
        )
        mock_llm_provider.structured_chat.return_value = llm_output

        # Execute
        results = await analyzer.analyze_batch(limit=10)

        # Verify: only 1 success
        assert len(results) == 1
        assert results[0].knowledge_id == "ko-1"
