"""Tests for Source Status Storage."""

import json
from datetime import datetime

import pytest

from app.models.status import SourceStatus
from app.storage.source_status import SourceStatusStorage


@pytest.fixture
def temp_status_file(tmp_path):
    """Provide a temporary file path for status testing."""
    return tmp_path / "test_status.json"


@pytest.fixture
def storage(temp_status_file):
    """Provide a SourceStatusStorage instance with temporary file."""
    return SourceStatusStorage(file_path=temp_status_file)


@pytest.fixture
def sample_status():
    """Provide a sample SourceStatus for testing."""
    return SourceStatus(
        source_name="test_rss",
        source_type="rss",
        is_active=False,
        last_checked=datetime(2026, 8, 22, 10, 0, 0),
        error_message="Connection timeout",
    )


def test_save_and_load_status(storage, sample_status):
    """Verify that a status can be saved and loaded correctly."""
    storage.save_status(sample_status)

    loaded = storage.get_status("test_rss")
    assert loaded is not None
    assert loaded.source_name == "test_rss"
    assert loaded.is_active is False
    assert loaded.error_message == "Connection timeout"
    assert loaded.last_checked == sample_status.last_checked


def test_get_all_statuses(storage, sample_status):
    """Verify that all statuses can be retrieved."""
    storage.save_status(sample_status)

    status2 = SourceStatus(
        source_name="test_gh",
        source_type="github",
        is_active=True,
    )
    storage.save_status(status2)

    all_statuses = storage.get_all_statuses()
    assert len(all_statuses) == 2

    names = {s.source_name for s in all_statuses}
    assert "test_rss" in names
    assert "test_gh" in names


def test_remove_status(storage, sample_status):
    """Verify that a status can be removed."""
    storage.save_status(sample_status)
    assert storage.get_status("test_rss") is not None

    storage.remove_status("test_rss")
    assert storage.get_status("test_rss") is None


def test_load_corrupted_file_returns_empty(storage, temp_status_file):
    """Verify that a corrupted file is handled gracefully."""
    temp_status_file.write_text("Invalid JSON {", encoding="utf-8")

    all_statuses = storage.get_all_statuses()
    assert all_statuses == []


def test_load_missing_file_returns_empty(storage, temp_status_file):
    """Verify that a missing file returns empty."""
    assert not temp_status_file.exists()

    loaded = storage.get_status("nonexistent")
    assert loaded is None

    all_statuses = storage.get_all_statuses()
    assert all_statuses == []


def test_atomic_write_overwrites_file(storage, temp_status_file, sample_status):
    """Verify that saving overwrites the file correctly without leaving temp files."""
    storage.save_status(sample_status)

    # Check that no .tmp files are left behind
    tmp_files = list(temp_status_file.parent.glob("*.tmp"))
    assert len(tmp_files) == 0

    # Verify content is valid JSON
    with open(temp_status_file, encoding="utf-8") as f:
        data = json.load(f)
    assert "test_rss" in data
