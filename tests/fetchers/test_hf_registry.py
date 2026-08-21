"""Tests for Hugging Face Source Registry implementation."""

import logging
from unittest.mock import MagicMock

import pytest

import app.fetchers.registry as registry_module
from app.config.settings import Settings
from app.fetchers.exceptions import DuplicateSourceError
from app.fetchers.registry import (
    ConfigBasedHFRegistry,
    get_hf_registry,
    initialize_hf_registry,
)
from app.models.source import HFSource, HFSourceType

# --- Fixtures ---


@pytest.fixture(autouse=True)
def reset_hf_singleton_state():
    """Reset the global HF registry state before and after each test."""
    registry_module._hf_registry = None
    yield
    registry_module._hf_registry = None


@pytest.fixture
def mock_settings():
    """Provide a mock Settings object."""
    settings = MagicMock(spec=Settings)
    settings.hf_sources = []
    return settings


# --- Tests for ConfigBasedHFRegistry ---


def test_register_source_success(mock_settings):
    """Verify that a source can be registered and retrieved."""
    registry = ConfigBasedHFRegistry(mock_settings)
    source = HFSource(name="bert", resource_id="google/bert", source_type=HFSourceType.MODEL)

    registry.register(source)

    result = registry.get_by_name("bert")
    assert result is source


def test_register_duplicate_source_raises_error(mock_settings):
    """Verify that registering a duplicate source raises DuplicateSourceError."""
    registry = ConfigBasedHFRegistry(mock_settings)
    source1 = HFSource(name="dup", resource_id="a/b", source_type=HFSourceType.MODEL)
    source2 = HFSource(name="dup", resource_id="c/d", source_type=HFSourceType.DATASET)

    registry.register(source1)

    with pytest.raises(DuplicateSourceError, match="HF Source with name 'dup'"):
        registry.register(source2)


def test_get_all_returns_all_sources(mock_settings):
    """Verify that get_all returns all registered sources."""
    registry = ConfigBasedHFRegistry(mock_settings)
    source1 = HFSource(name="s1", resource_id="a/b", source_type=HFSourceType.MODEL)
    source2 = HFSource(name="s2", resource_id="c/d", source_type=HFSourceType.DATASET)

    registry.register(source1)
    registry.register(source2)

    result = registry.get_all()
    assert len(result) == 2
    assert source1 in result
    assert source2 in result


def test_get_by_name_not_found_raises_error(mock_settings):
    """Verify that getting a non-existent source raises KeyError."""
    registry = ConfigBasedHFRegistry(mock_settings)

    with pytest.raises(KeyError, match="HF Source 'missing' not found"):
        registry.get_by_name("missing")


# --- Tests for Configuration Loading ---


def test_registry_loads_from_settings():
    """Verify that the registry automatically loads sources from settings."""
    settings = MagicMock(spec=Settings)
    settings.hf_sources = [
        {"name": "bert", "resource_id": "google/bert", "source_type": "model"},
        {"name": "squad", "resource_id": "rajpurkar/squad", "source_type": "dataset"},
    ]

    registry = ConfigBasedHFRegistry(settings)

    assert len(registry.get_all()) == 2
    assert registry.get_by_name("bert").source_type == HFSourceType.MODEL
    assert registry.get_by_name("squad").source_type == HFSourceType.DATASET


def test_registry_skips_invalid_config(caplog):
    """Verify that invalid config items (missing fields) are skipped."""
    settings = MagicMock(spec=Settings)
    settings.hf_sources = [
        {"name": "valid", "resource_id": "a/b", "source_type": "model"},
        {"name": "no_resource", "source_type": "model"},  # Missing resource_id
        {"resource_id": "a/b", "source_type": "model"},  # Missing name
    ]

    with caplog.at_level(logging.WARNING):
        registry = ConfigBasedHFRegistry(settings)

    assert len(registry.get_all()) == 1
    assert registry.get_by_name("valid").resource_id == "a/b"
    assert "Skipping invalid HF source config" in caplog.text


def test_registry_skips_invalid_source_type(caplog):
    """Verify that config items with invalid 'source_type' are skipped."""
    settings = MagicMock(spec=Settings)
    settings.hf_sources = [
        {"name": "valid", "resource_id": "a/b", "source_type": "model"},
        {"name": "invalid_type", "resource_id": "c/d", "source_type": "unknown_type"},
    ]

    with caplog.at_level(logging.WARNING):
        registry = ConfigBasedHFRegistry(settings)

    assert len(registry.get_all()) == 1
    assert "Skipping HF source config with invalid 'source_type'" in caplog.text


def test_registry_skips_duplicate_in_config(caplog):
    """Verify that duplicate sources in config are skipped."""
    settings = MagicMock(spec=Settings)
    settings.hf_sources = [
        {"name": "dup", "resource_id": "a/b", "source_type": "model"},
        {"name": "dup", "resource_id": "c/d", "source_type": "dataset"},
    ]

    with caplog.at_level(logging.WARNING):
        registry = ConfigBasedHFRegistry(settings)

    assert len(registry.get_all()) == 1
    assert registry.get_by_name("dup").resource_id == "a/b"
    assert "Skipping duplicate HF source in config" in caplog.text


# --- Tests for Singleton Access Path ---


def test_initialize_hf_registry_creates_singleton():
    """Verify that initialize_hf_registry creates the global instance."""
    settings = MagicMock(spec=Settings)
    settings.hf_sources = [{"name": "test", "resource_id": "a/b", "source_type": "model"}]

    initialize_hf_registry(settings)

    result = get_hf_registry()
    assert isinstance(result, ConfigBasedHFRegistry)
    assert len(result.get_all()) == 1


def test_initialize_hf_registry_is_idempotent():
    """Verify that calling initialize twice does not overwrite the existing instance."""
    settings1 = MagicMock(spec=Settings)
    settings1.hf_sources = [{"name": "first", "resource_id": "a/b", "source_type": "model"}]

    settings2 = MagicMock(spec=Settings)
    settings2.hf_sources = [{"name": "second", "resource_id": "c/d", "source_type": "dataset"}]

    initialize_hf_registry(settings1)
    first_registry = get_hf_registry()

    initialize_hf_registry(settings2)  # Should be ignored
    second_registry = get_hf_registry()

    assert first_registry is second_registry
    assert len(second_registry.get_all()) == 1


def test_get_hf_registry_raises_if_not_initialized():
    """Verify that get_hf_registry raises RuntimeError if not initialized."""
    with pytest.raises(RuntimeError, match="Hugging Face registry is not initialized"):
        get_hf_registry()
