"""Extraction services for knowledge processing pipeline.

This module contains services that use LLM to extract structured metadata
from normalized articles, with security guardrails against prompt injection.
"""

from .content_sanitizer import ContentSanitizer
from .metadata_extractor import MetadataExtractor
from .metadata_validator import MetadataValidator

__all__ = [
    "ContentSanitizer",
    "MetadataExtractor",
    "MetadataValidator",
]
