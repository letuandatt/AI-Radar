"""Core utility functions shared across the application."""

import hashlib
import re
from urllib.parse import urlparse, urlunparse

# Regex to collapse multiple whitespace characters into a single space
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_url(url: str) -> str:
    """Normalize a URL for consistent hashing.

    Normalization steps:
    1. Strip leading/trailing whitespace
    2. Lowercase the scheme and netloc (domain)
    3. Remove fragment identifier (#...)
    4. Remove trailing slash from path

    Args:
        url: The URL to normalize.

    Returns:
        Normalized URL string.
    """
    url = url.strip()

    try:
        parsed = urlparse(url)

        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")

        normalized = urlunparse(
            (
                scheme,
                netloc,
                path,
                parsed.params,
                parsed.query,
                "",  # Remove fragment
            )
        )

        return normalized
    except Exception:
        return url.lower()


def normalize_title(title: str) -> str:
    """Normalize a title for consistent hashing.

    Normalization steps:
    1. Strip leading/trailing whitespace
    2. Convert to lowercase
    3. Collapse multiple whitespace into single space

    Args:
        title: The title to normalize.

    Returns:
        Normalized title string.
    """
    title = title.strip().lower()
    title = _WHITESPACE_PATTERN.sub(" ", title)
    return title


def compute_content_hash(url: str, title: str) -> str:
    """Compute a SHA-256 hash for content deduplication.

    The hash is computed over the normalized URL and Title, ensuring
    that articles with the same URL and title (regardless of formatting
    differences) are detected as duplicates.

    Args:
        url: The article URL.
        title: The article title.

    Returns:
        Hexadecimal SHA-256 hash string.
    """
    normalized_url = normalize_url(url)
    normalized_title = normalize_title(title)

    content = f"{normalized_url}|{normalized_title}"

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_text_hash(text: str) -> str:
    """Compute SHA-256 hash of raw text content"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
