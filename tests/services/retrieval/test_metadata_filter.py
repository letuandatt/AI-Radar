"""Unit tests for MetadataFilterEngine."""

from datetime import datetime, timedelta, timezone

import pytest
from qdrant_client.http import models as qdrant_models

from app.services.retrieval.filter_models import (
    FilterCombination,
    FilterSeverity,
    MetadataFilter,
)
from app.services.retrieval.metadata_filter import MetadataFilterEngine

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def engine() -> MetadataFilterEngine:
    """Create a MetadataFilterEngine instance."""
    return MetadataFilterEngine()


# =============================================================================
# build_qdrant_filter Tests
# =============================================================================


class TestBuildQdrantFilter:
    """Tests for build_qdrant_filter method."""

    def test_empty_filter_returns_none(self, engine) -> None:
        """Empty filter returns None (match all)."""
        metadata_filter = MetadataFilter()
        result = engine.build_qdrant_filter(metadata_filter)
        assert result is None

    def test_single_value_filter_source_type(self, engine) -> None:
        """Single source_type filter produces MatchValue condition."""
        metadata_filter = MetadataFilter(source_type="github")
        result = engine.build_qdrant_filter(metadata_filter)

        assert result is not None
        assert len(result.must) == 1

        condition = result.must[0]
        assert isinstance(condition, qdrant_models.FieldCondition)
        assert condition.key == "source_type"
        assert isinstance(condition.match, qdrant_models.MatchValue)
        assert condition.match.value == "github"

    def test_single_value_filter_source_name(self, engine) -> None:
        """Single source_name filter produces MatchValue condition."""
        metadata_filter = MetadataFilter(source_name="techcrunch")
        result = engine.build_qdrant_filter(metadata_filter)

        assert result is not None
        assert len(result.must) == 1
        assert result.must[0].key == "source_name"
        assert result.must[0].match.value == "techcrunch"

    def test_multi_value_filter_topics(self, engine) -> None:
        """Multi-value topics filter produces MatchAny condition."""
        metadata_filter = MetadataFilter(topics=["LLM", "RAG"])
        result = engine.build_qdrant_filter(metadata_filter)

        assert result is not None
        assert len(result.must) == 1

        condition = result.must[0]
        assert condition.key == "topics"
        assert isinstance(condition.match, qdrant_models.MatchAny)
        assert condition.match.any == ["LLM", "RAG"]

    def test_multi_value_filter_entities(self, engine) -> None:
        """Multi-value entities filter produces MatchAny condition."""
        metadata_filter = MetadataFilter(entities=["OpenAI", "Anthropic"])
        result = engine.build_qdrant_filter(metadata_filter)

        assert result is not None
        condition = result.must[0]
        assert condition.key == "entities"
        assert isinstance(condition.match, qdrant_models.MatchAny)
        assert condition.match.any == ["OpenAI", "Anthropic"]

    def test_multi_value_filter_source_names(self, engine) -> None:
        """Multi-value source_names filter produces MatchAny condition."""
        metadata_filter = MetadataFilter(source_names=["cnn", "bbc", "reuters"])
        result = engine.build_qdrant_filter(metadata_filter)

        assert result is not None
        condition = result.must[0]
        assert condition.key == "source_name"
        assert isinstance(condition.match, qdrant_models.MatchAny)
        assert len(condition.match.any) == 3

    def test_range_filter_published_after(self, engine) -> None:
        """published_after produces Range with gte as Unix timestamp."""
        now = datetime.now(timezone.utc)
        metadata_filter = MetadataFilter(published_after=now)
        result = engine.build_qdrant_filter(metadata_filter)

        assert result is not None
        condition = result.must[0]
        assert condition.key == "published_at"
        assert condition.range.gte == now.timestamp()
        assert condition.range.lte is None

    def test_range_filter_published_before(self, engine) -> None:
        """published_before produces Range with lte as Unix timestamp."""
        now = datetime.now(timezone.utc)
        metadata_filter = MetadataFilter(published_before=now)
        result = engine.build_qdrant_filter(metadata_filter)

        assert result is not None
        condition = result.must[0]
        assert condition.key == "published_at"
        assert condition.range.lte == now.timestamp()
        assert condition.range.gte is None

    def test_range_filter_both_bounds(self, engine) -> None:
        """published_after + published_before produces Range with gte and lte."""
        now = datetime.now(timezone.utc)
        before = now - timedelta(days=7)

        metadata_filter = MetadataFilter(
            published_after=before,
            published_before=now,
        )
        result = engine.build_qdrant_filter(metadata_filter)

        assert result is not None
        condition = result.must[0]
        assert condition.key == "published_at"
        assert condition.range.gte == before.timestamp()
        assert condition.range.lte == now.timestamp()

    def test_has_url_true(self, engine) -> None:
        """has_url=True produces must_not IsEmptyCondition."""
        metadata_filter = MetadataFilter(has_url=True)
        result = engine.build_qdrant_filter(metadata_filter)

        assert result is not None
        # has_url=True → must_not contains IsEmptyCondition
        assert result.must_not is not None
        assert len(result.must_not) == 1
        condition = result.must_not[0]
        assert isinstance(condition, qdrant_models.IsEmptyCondition)

    def test_has_url_false(self, engine) -> None:
        """has_url=False produces must IsEmptyCondition."""
        metadata_filter = MetadataFilter(has_url=False)
        result = engine.build_qdrant_filter(metadata_filter)

        assert result is not None
        # has_url=False → must contains IsEmptyCondition
        assert result.must is not None
        assert len(result.must) == 1
        condition = result.must[0]
        assert isinstance(condition, qdrant_models.IsEmptyCondition)

    def test_complex_filter_multiple_conditions(self, engine) -> None:
        """Complex filter with multiple fields produces multiple must conditions."""
        now = datetime.now(timezone.utc)
        metadata_filter = MetadataFilter(
            source_type="rss",
            topics=["AI", "ML"],
            published_after=now - timedelta(days=30),
            has_url=True,
        )
        result = engine.build_qdrant_filter(metadata_filter)

        assert result is not None

        assert result.must is not None
        assert len(result.must) == 3

        keys = [c.key for c in result.must if hasattr(c, "key")]
        assert "source_type" in keys
        assert "topics" in keys
        assert "published_at" in keys

    def test_empty_multi_value_list_ignored(self, engine) -> None:
        """Empty multi-value lists are ignored (no condition added)."""
        metadata_filter = MetadataFilter(topics=[])
        result = engine.build_qdrant_filter(metadata_filter)

        # Empty list should not produce a condition
        assert result is None


# =============================================================================
# build_qdrant_filter_from_combination Tests
# =============================================================================


class TestBuildQdrantFilterCombination:
    """Tests for build_qdrant_filter_from_combination method."""

    def test_empty_combination_returns_none(self, engine) -> None:
        """Empty combination returns None."""
        combination = FilterCombination(filters=[])
        result = engine.build_qdrant_filter_from_combination(combination)
        assert result is None

    def test_and_combination(self, engine) -> None:
        """AND combination produces must filter."""
        f1 = MetadataFilter(source_type="rss")
        f2 = MetadataFilter(source_type="github")

        combination = FilterCombination(filters=[f1, f2], operator="and")
        result = engine.build_qdrant_filter_from_combination(combination)

        assert result is not None
        assert result.must is not None
        assert len(result.must) == 2

    def test_or_combination(self, engine) -> None:
        """OR combination produces should filter."""
        f1 = MetadataFilter(source_type="rss")
        f2 = MetadataFilter(source_type="github")

        combination = FilterCombination(filters=[f1, f2], operator="or")
        result = engine.build_qdrant_filter_from_combination(combination)

        assert result is not None
        assert result.should is not None
        assert len(result.should) == 2


# =============================================================================
# validate_filter Tests
# =============================================================================


class TestValidateFilter:
    """Tests for validate_filter method."""

    def test_valid_filter_returns_no_errors(self, engine) -> None:
        """Valid filter returns empty error list."""
        metadata_filter = MetadataFilter(
            source_type="rss",
            topics=["AI"],
        )
        errors = engine.validate_filter(metadata_filter)
        assert len(errors) == 0

    def test_invalid_date_range(self, engine) -> None:
        """published_after > published_before produces error."""
        now = datetime.now(timezone.utc)
        metadata_filter = MetadataFilter(
            published_after=now,
            published_before=now - timedelta(days=7),
        )
        errors = engine.validate_filter(metadata_filter)

        assert len(errors) == 1
        assert errors[0].field == "published_after/published_before"
        assert errors[0].severity == FilterSeverity.ERROR

    def test_valid_date_range(self, engine) -> None:
        """published_after < published_before produces no error."""
        now = datetime.now(timezone.utc)
        metadata_filter = MetadataFilter(
            published_after=now - timedelta(days=7),
            published_before=now,
        )
        errors = engine.validate_filter(metadata_filter)
        assert len(errors) == 0

    def test_list_too_large(self, engine) -> None:
        """List with more than 100 items produces error."""
        large_list = [f"topic_{i}" for i in range(101)]
        metadata_filter = MetadataFilter(topics=large_list)
        errors = engine.validate_filter(metadata_filter)

        assert len(errors) == 1
        assert errors[0].field == "topics"
        assert errors[0].severity == FilterSeverity.ERROR
        assert "100" in errors[0].message

    def test_empty_list_warning(self, engine) -> None:
        """Empty list produces warning."""
        metadata_filter = MetadataFilter(topics=[])
        errors = engine.validate_filter(metadata_filter)

        assert len(errors) == 1
        assert errors[0].severity == FilterSeverity.WARNING

    def test_multiple_errors(self, engine) -> None:
        """Multiple validation errors are all reported."""
        now = datetime.now(timezone.utc)
        metadata_filter = MetadataFilter(
            published_after=now,
            published_before=now - timedelta(days=7),
            topics=[f"t_{i}" for i in range(101)],
            entities=[],
        )
        errors = engine.validate_filter(metadata_filter)

        # 1 date error + 1 topics size error + 1 entities empty warning
        assert len(errors) == 3


# =============================================================================
# estimate_selectivity Tests
# =============================================================================


class TestEstimateSelectivity:
    """Tests for estimate_selectivity method."""

    def test_empty_filter_returns_1(self, engine) -> None:
        """Empty filter matches all (selectivity 1.0)."""
        metadata_filter = MetadataFilter()
        selectivity = engine.estimate_selectivity(metadata_filter)
        assert selectivity == 1.0

    def test_single_filter_reduces_selectivity(self, engine) -> None:
        """Single filter reduces selectivity below 1.0."""
        metadata_filter = MetadataFilter(source_type="github")
        selectivity = engine.estimate_selectivity(metadata_filter)
        assert 0.0 < selectivity < 1.0

    def test_multiple_filters_reduce_selectivity(self, engine) -> None:
        """Multiple filters reduce selectivity further."""
        single = MetadataFilter(source_type="github")
        multi = MetadataFilter(
            source_type="github",
            topics=["AI"],
            has_url=True,
        )

        single_selectivity = engine.estimate_selectivity(single)
        multi_selectivity = engine.estimate_selectivity(multi)

        assert multi_selectivity < single_selectivity

    def test_selectivity_bounded(self, engine) -> None:
        """Selectivity is always between 0.0 and 1.0."""
        metadata_filter = MetadataFilter(
            source_type="rss",
            source_name="cnn",
            source_names=["a", "b"],
            topics=["t1", "t2"],
            entities=["e1"],
            published_after=datetime.now(timezone.utc),
            published_before=datetime.now(timezone.utc) + timedelta(days=1),
            has_url=True,
        )
        selectivity = engine.estimate_selectivity(metadata_filter)
        assert 0.0 <= selectivity <= 1.0


# =============================================================================
# MetadataFilter Model Tests
# =============================================================================


class TestMetadataFilterModel:
    """Tests for MetadataFilter Pydantic model."""

    def test_is_empty_default(self) -> None:
        """Default MetadataFilter is empty."""
        metadata_filter = MetadataFilter()
        assert metadata_filter.is_empty() is True

    def test_is_empty_with_values(self) -> None:
        """MetadataFilter with values is not empty."""
        metadata_filter = MetadataFilter(source_type="rss")
        assert metadata_filter.is_empty() is False

    def test_active_field_count(self) -> None:
        """active_field_count returns correct count."""
        metadata_filter = MetadataFilter(
            source_type="rss",
            topics=["AI"],
            has_url=True,
        )
        assert metadata_filter.active_field_count() == 3

    def test_active_field_count_date_range(self) -> None:
        """Date range counts as 1 active field."""
        now = datetime.now(timezone.utc)
        metadata_filter = MetadataFilter(
            published_after=now - timedelta(days=7),
            published_before=now,
        )
        assert metadata_filter.active_field_count() == 1


# =============================================================================
# FilterCombination Model Tests
# =============================================================================


class TestFilterCombinationModel:
    """Tests for FilterCombination Pydantic model."""

    def test_valid_and_operator(self) -> None:
        """AND operator is valid."""
        combination = FilterCombination(operator="and")
        errors = combination.validate_operator()
        assert len(errors) == 0

    def test_valid_or_operator(self) -> None:
        """OR operator is valid."""
        combination = FilterCombination(operator="or")
        errors = combination.validate_operator()
        assert len(errors) == 0

    def test_invalid_operator(self) -> None:
        """Invalid operator produces error."""
        combination = FilterCombination(operator="xor")
        errors = combination.validate_operator()
        assert len(errors) == 1
        assert errors[0].field == "operator"
