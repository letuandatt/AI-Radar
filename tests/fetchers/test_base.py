"""Tests for Fetchers base contracts."""

import inspect

from app.fetchers.base import Parser, SourceRegistry
from app.fetchers.exceptions import DuplicateSourceError, FetcherError, ParsingError


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


def test_parser_protocol_exists():
    """Verify that the Parser protocol is defined."""
    assert Parser is not None


def test_parser_defines_required_methods():
    """Verify that the Parser protocol defines the exact parsing contract."""
    import inspect

    required_methods = {"parse"}

    protocol_members = {name for name, _ in inspect.getmembers(Parser) if not name.startswith("_")}

    assert required_methods.issubset(protocol_members)


def test_parsing_error_hierarchy():
    """Verify that ParsingError inherits from FetcherError."""
    assert issubclass(ParsingError, FetcherError)
