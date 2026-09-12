"""Metadata Filtering Engine.

Converts typed MetadataFilter models into Qdrant filter DSL
for pre-filtering before vector search.

Implements RAG-001 Multi-faceted Filtering strategy.
"""

from qdrant_client.http import models as qdrant_models

from app.core.logger import get_logger
from app.services.retrieval.filter_models import (
    FilterCombination,
    FilterSeverity,
    FilterValidationError,
    MetadataFilter,
)

logger = get_logger(__name__)

# Maximum allowed items in multi-value filter lists
MAX_LIST_SIZE = 100


class MetadataFilterEngine:
    """Engine for building and validating Qdrant metadata filters.

    Converts Pydantic MetadataFilter models into Qdrant filter DSL,
    validates filter correctness, and estimates selectivity.
    """

    # ------------------------------------------------------------------
    # Build Qdrant Filter
    # ------------------------------------------------------------------

    def build_qdrant_filter(self, metadata_filter: MetadataFilter) -> qdrant_models.Filter | None:
        """Convert MetadataFilter to Qdrant Filter DSL.

        Args:
            metadata_filter: The metadata filter to convert.

        Returns:
            Qdrant Filter object, or None if filter is empty.
        """
        if metadata_filter.is_empty():
            return None

        must_conditions: list = []
        must_not_conditions: list = []

        # source_type: single value match
        if metadata_filter.source_type is not None:
            must_conditions.append(
                qdrant_models.FieldCondition(
                    key="source_type",
                    match=qdrant_models.MatchValue(value=metadata_filter.source_type),
                )
            )

        # source_name: single value match
        if metadata_filter.source_name is not None:
            must_conditions.append(
                qdrant_models.FieldCondition(
                    key="source_name",
                    match=qdrant_models.MatchValue(value=metadata_filter.source_name),
                )
            )

        # source_names: multi-value match (OR within field)
        if metadata_filter.source_names is not None and len(metadata_filter.source_names) > 0:
            must_conditions.append(
                qdrant_models.FieldCondition(
                    key="source_name",
                    match=qdrant_models.MatchAny(any=metadata_filter.source_names),
                )
            )

        # topics: multi-value match (OR within field)
        if metadata_filter.topics is not None and len(metadata_filter.topics) > 0:
            must_conditions.append(
                qdrant_models.FieldCondition(
                    key="topics",
                    match=qdrant_models.MatchAny(any=metadata_filter.topics),
                )
            )

        # entities: multi-value match (OR within field)
        if metadata_filter.entities is not None and len(metadata_filter.entities) > 0:
            must_conditions.append(
                qdrant_models.FieldCondition(
                    key="entities",
                    match=qdrant_models.MatchAny(any=metadata_filter.entities),
                )
            )

        # published_at: range filter
        if (
            metadata_filter.published_after is not None
            or metadata_filter.published_before is not None
        ):
            range_params: dict = {}

            if metadata_filter.published_after is not None:
                range_params["gte"] = metadata_filter.published_after.timestamp()

            if metadata_filter.published_before is not None:
                range_params["lte"] = metadata_filter.published_before.timestamp()

            must_conditions.append(
                qdrant_models.FieldCondition(
                    key="published_at",
                    range=qdrant_models.Range(**range_params),
                )
            )

        # has_url: presence check on source_url
        if metadata_filter.has_url is not None:
            if metadata_filter.has_url:
                # has_url=True → source_url must NOT be empty
                # Express as: must_not IsEmpty(source_url)
                must_not_conditions.append(
                    qdrant_models.IsEmptyCondition(
                        is_empty=qdrant_models.PayloadField(key="source_url"),
                    )
                )
            else:
                # has_url=False → source_url must be empty
                # Express as: must IsEmpty(source_url)
                must_conditions.append(
                    qdrant_models.IsEmptyCondition(
                        is_empty=qdrant_models.PayloadField(key="source_url"),
                    )
                )

        if not must_conditions and not must_not_conditions:
            return None

        return qdrant_models.Filter(
            must=must_conditions if must_conditions else None,
            must_not=must_not_conditions if must_not_conditions else None,
        )

    # ------------------------------------------------------------------
    # Build Qdrant Filter from Combination
    # ------------------------------------------------------------------

    def build_qdrant_filter_from_combination(
        self, combination: FilterCombination
    ) -> qdrant_models.Filter | None:
        """Convert FilterCombination to Qdrant Filter DSL.

        Args:
            combination: The filter combination to convert.

        Returns:
            Qdrant Filter object, or None if combination is empty.
        """
        if not combination.filters:
            return None

        sub_filters: list[qdrant_models.Filter] = []
        for f in combination.filters:
            qf = self.build_qdrant_filter(f)
            if qf is not None:
                sub_filters.append(qf)

        if not sub_filters:
            return None

        if combination.operator == "and":
            return qdrant_models.Filter(must=sub_filters)  # type: ignore[arg-type]
        elif combination.operator == "or":
            return qdrant_models.Filter(should=sub_filters)  # type: ignore[arg-type]
        else:
            # Default to AND for unknown operators
            logger.warning(
                "Unknown filter operator '%s', defaulting to AND",
                combination.operator,
            )
            return qdrant_models.Filter(must=sub_filters)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Validate Filter
    # ------------------------------------------------------------------

    def validate_filter(self, metadata_filter: MetadataFilter) -> list[FilterValidationError]:
        """Validate a MetadataFilter for correctness.

        Checks:
        - Date range validity (after < before)
        - List sizes (max 100 items)
        - Empty multi-value lists

        Args:
            metadata_filter: The filter to validate.

        Returns:
            List of validation errors (empty if valid).
        """
        errors: list[FilterValidationError] = []

        # Check date range
        if (
            metadata_filter.published_after is not None
            and metadata_filter.published_before is not None
        ):
            if metadata_filter.published_after >= metadata_filter.published_before:
                errors.append(
                    FilterValidationError(
                        field="published_after/published_before",
                        message=(
                            f"published_after ({metadata_filter.published_after}) "
                            f"must be before published_before ({metadata_filter.published_before})"
                        ),
                        severity=FilterSeverity.ERROR,
                    )
                )

        # Check list sizes
        list_fields = [
            ("source_names", metadata_filter.source_names),
            ("topics", metadata_filter.topics),
            ("entities", metadata_filter.entities),
        ]

        for field_name, field_value in list_fields:
            if field_value is not None:
                if len(field_value) > MAX_LIST_SIZE:
                    errors.append(
                        FilterValidationError(
                            field=field_name,
                            message=(
                                f"List size {len(field_value)} exceeds maximum "
                                f"of {MAX_LIST_SIZE} items"
                            ),
                            severity=FilterSeverity.ERROR,
                        )
                    )
                elif len(field_value) == 0:
                    errors.append(
                        FilterValidationError(
                            field=field_name,
                            message="Empty list provided — use None instead of empty list",
                            severity=FilterSeverity.WARNING,
                        )
                    )

        return errors

    # ------------------------------------------------------------------
    # Estimate Selectivity
    # ------------------------------------------------------------------

    def estimate_selectivity(self, metadata_filter: MetadataFilter) -> float:
        """Estimate the percentage of data matching the filter.

        This is a heuristic estimate used for query optimization.
        Returns a value between 0.0 and 1.0.

        Args:
            metadata_filter: The filter to estimate.

        Returns:
            Estimated selectivity (0.0 = no matches, 1.0 = all match).
        """
        if metadata_filter.is_empty():
            return 1.0

        selectivity = 1.0

        # Single value filters: assume ~10% match each
        if metadata_filter.source_type is not None:
            selectivity *= 0.1

        if metadata_filter.source_name is not None:
            selectivity *= 0.05

        # Multi-value filters: assume ~20% match each
        if metadata_filter.source_names is not None and len(metadata_filter.source_names) > 0:
            selectivity *= 0.2

        if metadata_filter.topics is not None and len(metadata_filter.topics) > 0:
            selectivity *= 0.15

        if metadata_filter.entities is not None and len(metadata_filter.entities) > 0:
            selectivity *= 0.15

        # Range filter: assume ~50% match
        if (
            metadata_filter.published_after is not None
            or metadata_filter.published_before is not None
        ):
            selectivity *= 0.5

        # has_url: assume ~80% have URLs
        if metadata_filter.has_url is not None:
            selectivity *= 0.8

        return max(0.0, min(1.0, selectivity))
