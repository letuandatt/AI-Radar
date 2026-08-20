"""Exceptions specific to the Fetchers layer.

This module defines the exception hierarchy for data acquisition errors.
"""


class FetcherError(Exception):
    """Base exception for all fetcher-related errors."""


class DuplicateSourceError(FetcherError):
    """Raised when attempting to register a source that already exists."""
