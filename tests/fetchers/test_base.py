"""Tests for Fetchers base contracts."""

import inspect

from app.fetchers.base import SourceRegistry
from app.fetchers.exceptions import DuplicateSourceError, FetcherError


def test_source_registry_protocol_exists():
    """Verify that the SourceRegistry protocol is defined."""
    assert SourceRegistry is not None


def test_source_registry_defines_required_methods():
    """Verify that the protocol defines the exact registration contract."""
    required_methods = {"register", "get_all", "get_by_name"}

    protocol_members = {
        name for name, _ in inspect.getmembers(SourceRegistry) if not name.startswith("_")
    }

    assert required_methods.issubset(protocol_members), (
        f"SourceRegistry is missing required methods. "
        f"Expected at least {required_methods}, found {protocol_members}"
    )


def test_fetcher_exception_hierarchy():
    """Verify that fetcher exceptions inherit from the base FetcherError."""
    assert issubclass(DuplicateSourceError, FetcherError)
    assert issubclass(DuplicateSourceError, Exception)
