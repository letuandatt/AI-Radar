"""Metadata Validation Service for Knowledge Processing.

This service acts as a guardrail to validate the sanity
and security of metadata extracted by the LLM before it enters
the Knowledge Object construction phase.
"""

import re

from app.core.logger import get_logger
from app.models.metadata import ExtractionResult
from app.models.validation import ValidationResult

logger = get_logger(__name__)

# Patterns indicating prompt injection or system prompt leakage in LLM output
_OUTPUT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"assistant\s*:\s*", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
]

# Patterns indicating potential secret leakage
_SECRET_PATTERNS = [
    re.compile(r"api[_\s]*key\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"password\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"token\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"secret\s*[:=]\s*\S+", re.IGNORECASE),
]


class MetadataValidator:
    """Validates ExtractionResult objects against business and security rules.

    This validator ensures that LLM-generated metadata is structurally sound
    and free from prompt injection attempts or secret leakage.

    Thread Safety:
        This class is stateless and thread-safe.
    """

    def validate(self, result: ExtractionResult) -> ValidationResult:
        """Validate a single ExtractionResult.

        Args:
            result: The ExtractionResult to validate.

        Returns:
            ValidationResult indicating success or failure with detailed reasons.
        """
        # 1. Validate relevance_score range
        if not (0.0 <= result.relevance_score <= 1.0):
            return ValidationResult.failure(
                error_message=f"relevance_score out of bounds: {result.relevance_score}",
                details={
                    "field": "relevance_score",
                    "actual_value": result.relevance_score,
                    "valid_range": "[0.0, 1.0]",
                },
            )

        # 2. Validate topics is not empty
        if not result.topics:
            return ValidationResult.failure(
                error_message="topics list is empty",
                details={"field": "topics", "actual_value": []},
            )

        # 3. Validate entities is not empty
        if not result.entities:
            return ValidationResult.failure(
                error_message="entities list is empty",
                details={"field": "entities", "actual_value": []},
            )

        # 4. SEC-001: Check summary for injection patterns or secrets
        for pattern in _OUTPUT_INJECTION_PATTERNS:
            if pattern.search(result.summary):
                return ValidationResult.failure(
                    error_message="summary contains potential prompt injection pattern",
                    details={
                        "field": "summary",
                        "pattern_matched": pattern.pattern,
                        "security_check": "SEC-001 injection detection",
                    },
                )

        for pattern in _SECRET_PATTERNS:
            if pattern.search(result.summary):
                return ValidationResult.failure(
                    error_message="summary contains potential secret leakage pattern",
                    details={
                        "field": "summary",
                        "pattern_matched": pattern.pattern,
                        "security_check": "SEC-001 secret redaction",
                    },
                )

        # 5. SEC-001: Check entities for injection patterns
        for entity in result.entities:
            for pattern in _OUTPUT_INJECTION_PATTERNS:
                if pattern.search(entity):
                    return ValidationResult.failure(
                        error_message=f"entity contains potential "
                        f"prompt injection pattern: '{entity}'",
                        details={
                            "field": "entities",
                            "pattern_matched": pattern.pattern,
                            "entity_value": entity,
                            "security_check": "SEC-001 injection detection",
                        },
                    )

        # All checks passed
        return ValidationResult.success(
            details={
                "topics_count": len(result.topics),
                "entities_count": len(result.entities),
                "relevance_score": result.relevance_score,
            }
        )
