"""Fetchers layer for data acquisition."""

from .registry import get_source_registry, initialize_source_registry

__all__ = [
    "get_source_registry",
    "initialize_source_registry",
]
