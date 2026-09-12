"""Validation service for KnowledgeObject integrity checks.

This module provides a validator that ensures KnowledgeObjects are
structurally sound, internally consistent, and safe to persist.
It acts as the final quality gate before objects enter the Knowledge Store.
"""

from app.core.logger import get_logger
from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.validation import ValidationResult

logger = get_logger(__name__)

# Mapping of source types to their expected URL domains
_SOURCE_URL_DOMAINS: dict[str, list[str]] = {
    "rss": [],  # RSS can come from any domain
    "github": ["github.com"],
    "huggingface": ["huggingface.co"],
}


class KnowledgeObjectValidator:
    """Validates KnowledgeObjects for structural and semantic integrity.

    This validator enforces a set of business rules to prevent malformed,
    inconsistent, or corrupted objects from entering the Knowledge Store.

    Thread Safety:
        This class is stateless and thread-safe.

    Example:
        validator = KnowledgeObjectValidator()
        result = validator.validate(knowledge_object)
        if not result.is_valid:
        ... logger.warning(result.error_message)
    """

    def validate(self, knowledge_object: KnowledgeObject) -> ValidationResult:
        """Validate a single KnowledgeObject against all integrity rules.

        Rules are checked sequentially. The first failure is returned
        immediately (early return pattern).

        Args:
            knowledge_object: The object to validate.

        Returns:
            ValidationResult with is_valid flag, error_message, and details.
        """
        # 1. Check id
        id_result = self._check_id(knowledge_object)
        if not id_result.is_valid:
            return id_result

        # 2. Check title
        title_result = self._check_title(knowledge_object)
        if not title_result.is_valid:
            return title_result

        # 3. Check content_text
        content_result = self._check_content_text(knowledge_object)
        if not content_result.is_valid:
            return content_result

        # 4. Check content_hash integrity
        hash_result = self._check_content_hash(knowledge_object)
        if not hash_result.is_valid:
            return hash_result

        # 5. Check source_url
        url_result = self._check_source_url(knowledge_object)
        if not url_result.is_valid:
            return url_result

        # 6. Check external_id requirement
        ext_id_result = self._check_external_id(knowledge_object)
        if not ext_id_result.is_valid:
            return ext_id_result

        # 7. Check metadata consistency
        metadata_result = self._check_metadata(knowledge_object)
        if not metadata_result.is_valid:
            return metadata_result

        # All checks passed
        return ValidationResult.success(
            details={
                "object_id": knowledge_object.id,
                "source_type": knowledge_object.source_type,
                "content_length": len(knowledge_object.content_text),
            }
        )

    def validate_batch(
        self, knowledge_objects: list[KnowledgeObject]
    ) -> tuple[list[KnowledgeObject], list[KnowledgeObject]]:
        """Validate a batch of KnowledgeObjects, partitioning into valid and invalid.

        Args:
            knowledge_objects: List of objects to validate.

        Returns:
            Tuple of (valid_objects, invalid_objects).
        """
        valid_objects: list[KnowledgeObject] = []
        invalid_objects: list[KnowledgeObject] = []

        for ko in knowledge_objects:
            result = self.validate(ko)
            if result.is_valid:
                valid_objects.append(ko)
            else:
                invalid_objects.append(ko)
                logger.warning(
                    "Invalid KnowledgeObject %s: %s",
                    ko.id,
                    result.error_message,
                )

        logger.info(
            "Validated %d objects: %d valid, %d invalid",
            len(knowledge_objects),
            len(valid_objects),
            len(invalid_objects),
        )

        return valid_objects, invalid_objects

    # ------------------------------------------------------------------
    # Private validation rules
    # ------------------------------------------------------------------

    def _check_id(self, ko: KnowledgeObject) -> ValidationResult:
        """Verify that the object has a non-empty identifier."""
        if not ko.id or not ko.id.strip():
            return ValidationResult.failure(
                error_message="id must not be empty",
                details={"field": "id", "object_id": ko.id},
            )
        return ValidationResult.success()

    def _check_title(self, ko: KnowledgeObject) -> ValidationResult:
        """Verify that title is non-empty."""
        if not ko.title or not ko.title.strip():
            return ValidationResult.failure(
                error_message="title must not be empty",
                details={"field": "title", "object_id": ko.id},
            )
        return ValidationResult.success()

    def _check_content_text(self, ko: KnowledgeObject) -> ValidationResult:
        """Verify that content_text is non-empty."""
        if not ko.content_text or not ko.content_text.strip():
            return ValidationResult.failure(
                error_message="content_text must not be empty",
                details={"field": "content_text", "object_id": ko.id},
            )
        return ValidationResult.success()

    def _check_content_hash(self, ko: KnowledgeObject) -> ValidationResult:
        """Verify that content_hash matches the SHA-256 of content_text."""
        expected_hash = compute_text_hash(ko.content_text)
        if ko.content_hash != expected_hash:
            return ValidationResult.failure(
                error_message="content_hash does not match content_text",
                details={
                    "field": "content_hash",
                    "object_id": ko.id,
                    "expected_prefix": expected_hash[:16],
                    "actual_prefix": ko.content_hash[:16],
                },
            )
        return ValidationResult.success()

    def _check_source_url(self, ko: KnowledgeObject) -> ValidationResult:
        """Verify that source_url is consistent with source_type."""
        if not ko.source_url or not ko.source_url.strip():
            return ValidationResult.failure(
                error_message="source_url must not be empty",
                details={"field": "source_url", "object_id": ko.id},
            )

        expected_domains = _SOURCE_URL_DOMAINS.get(ko.source_type, [])
        if not expected_domains:
            # No domain restriction for this source type (e.g., RSS)
            return ValidationResult.success()

        url_lower = ko.source_url.lower()
        if not any(domain in url_lower for domain in expected_domains):
            return ValidationResult.failure(
                error_message=(
                    f"source_url does not match expected domain(s) "
                    f"for source_type '{ko.source_type}'"
                ),
                details={
                    "field": "source_url",
                    "object_id": ko.id,
                    "source_url": ko.source_url,
                    "expected_domains": expected_domains,
                },
            )
        return ValidationResult.success()

    def _check_external_id(self, ko: KnowledgeObject) -> ValidationResult:
        """Verify that external_id is present for source types that require it."""
        required_types = {"github", "huggingface"}
        if ko.source_type in required_types:
            if not ko.external_id or not ko.external_id.strip():
                return ValidationResult.failure(
                    error_message=(
                        f"external_id must not be empty for source_type '{ko.source_type}'"
                    ),
                    details={
                        "field": "external_id",
                        "object_id": ko.id,
                        "source_type": ko.source_type,
                    },
                )
        return ValidationResult.success()

    def _check_metadata(self, ko: KnowledgeObject) -> ValidationResult:
        """Verify metadata consistency rules."""
        metadata = ko.metadata

        # Relevance score must be within valid range
        if not 0.0 <= metadata.relevance_score <= 1.0:
            return ValidationResult.failure(
                error_message="metadata.relevance_score out of valid range",
                details={
                    "field": "metadata.relevance_score",
                    "object_id": ko.id,
                    "actual_value": metadata.relevance_score,
                    "valid_range": "[0.0, 1.0]",
                },
            )

        # Topics must not be empty
        if not metadata.topics:
            return ValidationResult.failure(
                error_message="metadata.topics must not be empty",
                details={"field": "metadata.topics", "object_id": ko.id},
            )

        # Entities must not be empty
        if not metadata.entities:
            return ValidationResult.failure(
                error_message="metadata.entities must not be empty",
                details={"field": "metadata.entities", "object_id": ko.id},
            )

        return ValidationResult.success()
