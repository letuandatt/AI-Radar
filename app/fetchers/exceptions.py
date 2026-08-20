"""Exceptions specific to the Fetchers layer.

This module defines the exception hierarchy for data acquisition errors,
including network, timeout, and HTTP status related issues.
"""


class FetcherError(Exception):
    """Base exception for all fetcher-related errors."""


class DuplicateSourceError(FetcherError):
    """Raised when attempting to register a source that already exists."""


# --- New Network & HTTP Exceptions ---


class NetworkError(FetcherError):
    """Raised when a network connection fails (e.g., DNS resolution, connection refused)."""


class FetchTimeoutError(FetcherError):
    """Raised when a fetch operation exceeds the allowed time limit."""


class HTTPStatusError(FetcherError):
    """Raised when the server returns an unsuccessful HTTP status code (4xx, 5xx)."""
