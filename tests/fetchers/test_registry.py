"""Tests for Source Registry implementation."""

from unittest.mock import MagicMock

import pytest

import app.fetchers.registry as registry_module
from app.config.settings import Settings
from app.fetchers.exceptions import DuplicateSourceError
from app.fetchers.registry import (
    ConfigBasedSourceRegistry,
    get_source_registry,
    initialize_source_registry,
)
from app.models.source import RSSSource

# --- Fixtures ---


@pytest.fixture(autouse=True)
def reset_singleton_state():
    """Reset the global registry state before and after each test."""
    registry_module._registry = None
    yield
    registry_module._registry = None


@pytest.fixture
def mock_settings():
    """Provide a mock Settings object."""
    settings = MagicMock(spec=Settings)
    settings.rss_sources = []
    return settings


# --- Tests for ConfigBasedSourceRegistry ---


def test_register_source_success(mock_settings):
    """Verify that a source can be registered and retrieved."""
    registry = ConfigBasedSourceRegistry(mock_settings)
    source = RSSSource(name="techcrunch", url="https://techcrunch.com/feed/")

    registry.register(source)

    result = registry.get_by_name("techcrunch")
    assert result is source


def test_register_duplicate_source_raises_error(mock_settings):
    """Verify that registering a duplicate source raises DuplicateSourceError."""
    registry = ConfigBasedSourceRegistry(mock_settings)
    source1 = RSSSource(name="duplicate", url="http://url1.com")
    source2 = RSSSource(name="duplicate", url="http://url2.com")

    registry.register(source1)

    with pytest.raises(DuplicateSourceError, match="Source with name 'duplicate'"):
        registry.register(source2)


def test_get_all_returns_all_sources(mock_settings):
    """Verify that get_all returns all registered sources."""
    registry = ConfigBasedSourceRegistry(mock_settings)
    source1 = RSSSource(name="source1", url="http://url1.com")
    source2 = RSSSource(name="source2", url="http://url2.com")

    registry.register(source1)
    registry.register(source2)

    result = registry.get_all()
    assert len(result) == 2
    assert source1 in result
    assert source2 in result


def test_get_by_name_not_found_raises_error(mock_settings):
    """Verify that getting a non-existent source raises KeyError."""
    registry = ConfigBasedSourceRegistry(mock_settings)

    with pytest.raises(KeyError, match="Source 'missing' not found"):
        registry.get_by_name("missing")


# --- Tests for Configuration Loading ---


def test_registry_loads_from_settings():
    """Verify that the registry automatically loads sources from settings."""
    settings = MagicMock(spec=Settings)
    settings.rss_sources = [
        {"name": "feed1", "url": "http://feed1.com/rss"},
        {"name": "feed2", "url": "http://feed2.com/rss"},
    ]

    registry = ConfigBasedSourceRegistry(settings)

    assert len(registry.get_all()) == 2
    assert registry.get_by_name("feed1").url == "http://feed1.com/rss"
    assert registry.get_by_name("feed2").url == "http://feed2.com/rss"


def test_registry_skips_invalid_config(caplog):
    """Verify that invalid config items (missing name/url) are skipped."""
    settings = MagicMock(spec=Settings)
    settings.rss_sources = [
        {"name": "valid", "url": "http://valid.com"},
        {"name": "no_url"},  # Missing url
        {"url": "http://no_name.com"},  # Missing name
    ]

    with caplog.at_level("WARNING"):
        registry = ConfigBasedSourceRegistry(settings)

    assert len(registry.get_all()) == 1
    assert registry.get_by_name("valid").url == "http://valid.com"
    assert "Skipping invalid RSS source config" in caplog.text


def test_registry_skips_duplicate_in_config(caplog):
    """Verify that duplicate sources in config are skipped."""
    settings = MagicMock(spec=Settings)
    settings.rss_sources = [
        {"name": "duplicate", "url": "http://first.com"},
        {"name": "duplicate", "url": "http://second.com"},
    ]

    with caplog.at_level("WARNING"):
        registry = ConfigBasedSourceRegistry(settings)

    assert len(registry.get_all()) == 1
    assert registry.get_by_name("duplicate").url == "http://first.com"
    assert "Skipping duplicate source in config" in caplog.text


# --- Tests for Singleton Access Path ---


def test_initialize_source_registry_creates_singleton():
    """Verify that initialize_source_registry creates the global instance."""
    settings = MagicMock(spec=Settings)
    settings.rss_sources = [{"name": "test", "url": "http://test.com"}]

    initialize_source_registry(settings)

    result = get_source_registry()
    assert isinstance(result, ConfigBasedSourceRegistry)
    assert len(result.get_all()) == 1


def test_initialize_source_registry_is_idempotent():
    """Verify that calling initialize twice does not overwrite the existing instance."""
    settings1 = MagicMock(spec=Settings)
    settings1.rss_sources = [{"name": "first", "url": "http://first.com"}]

    settings2 = MagicMock(spec=Settings)
    settings2.rss_sources = [{"name": "second", "url": "http://second.com"}]

    initialize_source_registry(settings1)
    first_registry = get_source_registry()

    initialize_source_registry(settings2)  # Should be ignored
    second_registry = get_source_registry()

    assert first_registry is second_registry
    assert len(second_registry.get_all()) == 1  # Still only has 'first'


def test_get_source_registry_raises_if_not_initialized():
    """Verify that get_source_registry raises RuntimeError if not initialized."""
    # _registry is None due to the autouse fixture
    with pytest.raises(RuntimeError, match="Source registry is not initialized"):
        get_source_registry()
