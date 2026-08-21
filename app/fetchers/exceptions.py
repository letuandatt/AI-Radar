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


class ParsingError(FetcherError):
    """Raised when raw data cannot be parsed into structured models.

    This typically indicates malformed XML/JSON or a fundamental
    incompatibility with the expected data format.
    """


class GitHubAPIError(FetcherError):
    """Raised when GitHub API returns an error response.

    This includes authentication failures (401/403), resource not found (404),
    validation errors (422), and rate limit exceeded (429).
    """


class HuggingFaceAPIError(FetcherError):
    """Raised when Hugging Face API returns an error response.

    This includes authentication failures (401/403), resource not found (404),
    and rate limit exceeded (429).
    """
