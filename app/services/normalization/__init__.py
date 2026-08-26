"""Normalization services for knowledge processing pipeline.

This module contains services that transform cleaned raw data into
a unified schema, preparing it for metadata extraction (Sprint 11).
"""

from .standardizer import DataStandardizer

__all__ = [
    "DataStandardizer",
]
