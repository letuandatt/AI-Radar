"""Unit tests for core utility functions (app/core/utils.py)."""

from app.core.utils import compute_text_hash


def test_compute_text_hash_deterministic() -> None:
    """Verify that the same text produces the same hash."""
    text = "Hello, World!"
    hash1 = compute_text_hash(text)
    hash2 = compute_text_hash(text)

    assert hash1 == hash2
    assert isinstance(hash1, str)
    assert len(hash1) == 64  # SHA-256 hex digest length


def test_compute_text_hash_different_content() -> None:
    """Verify that different texts produce different hashes."""
    hash1 = compute_text_hash("Hello")
    hash2 = compute_text_hash("World")

    assert hash1 != hash2


def test_compute_text_hash_empty_string() -> None:
    """Verify that empty string produces a valid hash."""
    hash_result = compute_text_hash("")

    assert isinstance(hash_result, str)
    assert len(hash_result) == 64
