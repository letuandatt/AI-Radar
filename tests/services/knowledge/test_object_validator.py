"""Unit tests for KnowledgeObjectValidator."""

from datetime import datetime

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.knowledge.object_validator import KnowledgeObjectValidator


@pytest.fixture
def validator() -> KnowledgeObjectValidator:
    """Provide a KnowledgeObjectValidator instance."""
    return KnowledgeObjectValidator()


@pytest.fixture
def sample_metadata() -> ExtractionResult:
    """Provide a valid ExtractionResult."""
    return ExtractionResult(
        summary="A concise summary.",
        topics=["AI", "Machine Learning"],
        entities=["OpenAI"],
        relevance_score=0.9,
    )


@pytest.fixture
def valid_knowledge_object(sample_metadata: ExtractionResult) -> KnowledgeObject:
    """Provide a fully valid KnowledgeObject."""
    content = "Artificial intelligence is transforming the world."
    return KnowledgeObject(
        source_type="rss",
        source_name="tech_blog",
        external_id="norm_id_123",
        source_url="https://example.com/future-of-ai",
        content_hash=compute_text_hash(content),
        fetched_at=datetime(2025, 1, 2, 10, 0, 0),
        published_at=datetime(2025, 1, 1, 12, 0, 0),
        parser_version="1.0.0",
        normalizer_version="1.0.0",
        extractor_version="1.0.0",
        title="The Future of AI",
        content_text=content,
        metadata=sample_metadata,
    )


def _make_object_with_overrides(base: KnowledgeObject, **overrides: object) -> KnowledgeObject:
    """Helper to create a KnowledgeObject with specific field overrides."""
    data = base.model_dump()
    data.update(overrides)
    return KnowledgeObject.model_validate(data)


# ==============================================================================
# Valid Object Tests
# ==============================================================================


class TestValidObject:
    """Tests that a fully valid object passes all checks."""

    def test_valid_object_passes(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        result = validator.validate(valid_knowledge_object)
        assert result.is_valid is True
        assert result.error_message is None
        assert result.details["object_id"] == valid_knowledge_object.id

    def test_valid_github_object(self, validator: KnowledgeObjectValidator) -> None:
        """GitHub object with matching domain and external_id should pass."""
        content = "New release notes."
        metadata = ExtractionResult(
            summary="Release notes.",
            topics=["DevOps"],
            entities=["GitHub"],
            relevance_score=0.8,
        )
        ko = KnowledgeObject(
            source_type="github",
            source_name="fastapi",
            external_id="commit_abc123",
            source_url="https://github.com/tiangolo/fastapi/releases",
            content_hash=compute_text_hash(content),
            fetched_at=datetime(2025, 1, 2),
            published_at=datetime(2025, 1, 1),
            title="FastAPI Release",
            content_text=content,
            metadata=metadata,
        )
        result = validator.validate(ko)
        assert result.is_valid is True

    def test_valid_huggingface_object(self, validator: KnowledgeObjectValidator) -> None:
        """HuggingFace object with matching domain and external_id should pass."""
        content = "New model card."
        metadata = ExtractionResult(
            summary="Model card.",
            topics=["NLP"],
            entities=["HuggingFace"],
            relevance_score=0.7,
        )
        ko = KnowledgeObject(
            source_type="huggingface",
            source_name="huggingface",
            external_id="model_xyz",
            source_url="https://huggingface.co/models/bert-base",
            content_hash=compute_text_hash(content),
            fetched_at=datetime(2025, 1, 2),
            published_at=None,
            title="BERT Base",
            content_text=content,
            metadata=metadata,
        )
        result = validator.validate(ko)
        assert result.is_valid is True


# ==============================================================================
# ID Validation Tests
# ==============================================================================


class TestIdValidation:
    """Tests for the id field validation rule."""

    def test_empty_id_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        ko = _make_object_with_overrides(valid_knowledge_object, id="")
        result = validator.validate(ko)
        assert result.is_valid is False
        assert "id must not be empty" in result.error_message
        assert result.details["field"] == "id"

    def test_whitespace_id_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        ko = _make_object_with_overrides(valid_knowledge_object, id="   ")
        result = validator.validate(ko)
        assert result.is_valid is False


# ==============================================================================
# Content Fields Validation Tests
# ==============================================================================


class TestContentFieldsValidation:
    """Tests for title and content_text validation rules."""

    def test_empty_title_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        ko = _make_object_with_overrides(valid_knowledge_object, title="")
        result = validator.validate(ko)
        assert result.is_valid is False
        assert "title must not be empty" in result.error_message

    def test_empty_content_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        ko = _make_object_with_overrides(
            valid_knowledge_object,
            content_text="",
            content_hash=compute_text_hash(""),
        )
        result = validator.validate(ko)
        assert result.is_valid is False
        assert "content_text must not be empty" in result.error_message


# ==============================================================================
# Content Hash Validation Tests
# ==============================================================================


class TestContentHashValidation:
    """Tests for content_hash integrity check."""

    def test_hash_mismatch_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        ko = _make_object_with_overrides(valid_knowledge_object, content_hash="invalid_hash_value")
        result = validator.validate(ko)
        assert result.is_valid is False
        assert "content_hash does not match" in result.error_message
        assert result.details["field"] == "content_hash"

    def test_correct_hash_passes(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        correct_hash = compute_text_hash(valid_knowledge_object.content_text)
        ko = _make_object_with_overrides(valid_knowledge_object, content_hash=correct_hash)
        result = validator.validate(ko)
        assert result.is_valid is True


# ==============================================================================
# Source URL Validation Tests
# ==============================================================================


class TestSourceUrlValidation:
    """Tests for source_url and source_type consistency."""

    def test_github_url_wrong_domain_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        ko = _make_object_with_overrides(
            valid_knowledge_object,
            source_type="github",
            source_url="https://example.com/repo",
            external_id="some_id",
        )
        result = validator.validate(ko)
        assert result.is_valid is False
        assert "does not match expected domain" in result.error_message

    def test_github_url_correct_domain_passes(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        ko = _make_object_with_overrides(
            valid_knowledge_object,
            source_type="github",
            source_url="https://github.com/user/repo",
            external_id="some_id",
        )
        result = validator.validate(ko)
        assert result.is_valid is True

    def test_empty_source_url_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        ko = _make_object_with_overrides(valid_knowledge_object, source_url="")
        result = validator.validate(ko)
        assert result.is_valid is False
        assert "source_url must not be empty" in result.error_message

    def test_rss_any_domain_passes(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        """RSS source type should accept any domain."""
        ko = _make_object_with_overrides(
            valid_knowledge_object,
            source_type="rss",
            source_url="https://any-random-blog.com/article",
        )
        result = validator.validate(ko)
        assert result.is_valid is True


# ==============================================================================
# External ID Validation Tests
# ==============================================================================


class TestExternalIdValidation:
    """Tests for external_id requirement based on source_type."""

    def test_github_missing_external_id_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        ko = _make_object_with_overrides(
            valid_knowledge_object,
            source_type="github",
            source_url="https://github.com/user/repo",
            external_id="",
        )
        result = validator.validate(ko)
        assert result.is_valid is False
        assert "external_id must not be empty" in result.error_message

    def test_huggingface_missing_external_id_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        ko = _make_object_with_overrides(
            valid_knowledge_object,
            source_type="huggingface",
            source_url="https://huggingface.co/models/bert",
            external_id="",
        )
        result = validator.validate(ko)
        assert result.is_valid is False

    def test_rss_missing_external_id_passes(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        """RSS does not require external_id."""
        ko = _make_object_with_overrides(valid_knowledge_object, external_id="")
        result = validator.validate(ko)
        assert result.is_valid is True


# ==============================================================================
# Metadata Validation Tests (Frankenstein Detection)
# ==============================================================================


class TestMetadataValidation:
    """Tests for metadata integrity rules including Frankenstein detection."""

    def test_summary_longer_than_content_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        """Frankenstein detection: summary must not exceed content length."""
        long_summary = "x" * (len(valid_knowledge_object.content_text) + 100)
        bad_metadata = ExtractionResult(
            summary=long_summary,
            topics=["AI"],
            entities=["OpenAI"],
            relevance_score=0.9,
        )
        ko = _make_object_with_overrides(valid_knowledge_object, metadata=bad_metadata)
        result = validator.validate(ko)
        assert result.is_valid is False
        assert "longer than content_text" in result.error_message
        assert result.details["field"] == "metadata.summary"

    def test_relevance_score_out_of_range_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        bad_metadata = ExtractionResult.model_construct(
            summary="Summary",
            topics=["AI"],
            entities=["OpenAI"],
            relevance_score=1.5,
        )
        ko = _make_object_with_overrides(valid_knowledge_object, metadata=bad_metadata)
        result = validator.validate(ko)
        assert result.is_valid is False
        assert "relevance_score out of valid range" in result.error_message

    def test_empty_topics_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        bad_metadata = ExtractionResult(
            summary="Summary",
            topics=[],
            entities=["OpenAI"],
            relevance_score=0.9,
        )
        ko = _make_object_with_overrides(valid_knowledge_object, metadata=bad_metadata)
        result = validator.validate(ko)
        assert result.is_valid is False
        assert "topics must not be empty" in result.error_message

    def test_empty_entities_fails(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        bad_metadata = ExtractionResult(
            summary="Summary",
            topics=["AI"],
            entities=[],
            relevance_score=0.9,
        )
        ko = _make_object_with_overrides(valid_knowledge_object, metadata=bad_metadata)
        result = validator.validate(ko)
        assert result.is_valid is False
        assert "entities must not be empty" in result.error_message


# ==============================================================================
# Batch Validation Tests
# ==============================================================================


class TestBatchValidation:
    """Tests for validate_batch partitioning logic."""

    def test_batch_all_valid(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        objects = [valid_knowledge_object, valid_knowledge_object]
        valid, invalid = validator.validate_batch(objects)
        assert len(valid) == 2
        assert len(invalid) == 0

    def test_batch_mixed(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        bad_object = _make_object_with_overrides(valid_knowledge_object, title="")
        objects = [valid_knowledge_object, bad_object]
        valid, invalid = validator.validate_batch(objects)
        assert len(valid) == 1
        assert len(invalid) == 1
        assert invalid[0].id == bad_object.id

    def test_batch_empty(self, validator: KnowledgeObjectValidator) -> None:
        valid, invalid = validator.validate_batch([])
        assert len(valid) == 0
        assert len(invalid) == 0

    def test_batch_all_invalid(
        self,
        validator: KnowledgeObjectValidator,
        valid_knowledge_object: KnowledgeObject,
    ) -> None:
        bad1 = _make_object_with_overrides(valid_knowledge_object, title="")
        bad2 = _make_object_with_overrides(valid_knowledge_object, content_hash="bad")
        valid, invalid = validator.validate_batch([bad1, bad2])
        assert len(valid) == 0
        assert len(invalid) == 2
