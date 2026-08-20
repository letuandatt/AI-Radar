"""Fetchers layer for data acquisition."""

from .registry import (
    get_github_registry,
    get_source_registry,
    initialize_github_registry,
    initialize_source_registry,
)

__all__ = [
    "get_source_registry",
    "initialize_source_registry",
    "get_github_registry",
    "initialize_github_registry",
]
