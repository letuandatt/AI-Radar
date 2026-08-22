"""Tests for History Storage implementation."""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.models.result import AcquisitionResult, SourceError
from app.storage.history import HistoryStorage, get_history_storage, save_acquisition_result


@pytest.fixture
def temp_history_file(tmp_path):
    """Provide a temporary file path for history testing."""
    return tmp_path / "test_history.json"


@pytest.fixture
def history_storage(temp_history_file):
    """Provide a HistoryStorage instance with temporary file."""
    return HistoryStorage(file_path=temp_history_file)


@pytest.fixture
def sample_result():
    """Provide a sample AcquisitionResult for testing."""
    return AcquisitionResult(
        timestamp=datetime(2026, 8, 22, 10, 0, 0),
        total_sources=5,
        successful_sources=4,
        failed_sources=1,
        total_articles=25,
        execution_time=3.5,
        errors=[
            SourceError(
                source_name="test_source",
                source_type="rss",
                error_type="NetworkError",
                error_message="Connection timeout",
            )
        ],
    )


# --- Test Save & Load ---


def test_save_and_load_result(history_storage, temp_history_file, sample_result):
    """Verify that an AcquisitionResult can be saved and loaded correctly."""
    # Save result
    history_storage.save_result(sample_result)

    # Verify file was created
    assert temp_history_file.exists()

    # Load history
    history = history_storage.get_history()

    # Assertions
    assert len(history) == 1
    loaded_result = history[0]

    assert loaded_result.total_sources == 5
    assert loaded_result.successful_sources == 4
    assert loaded_result.failed_sources == 1
    assert loaded_result.total_articles == 25
    assert loaded_result.execution_time == 3.5
    assert len(loaded_result.errors) == 1
    assert loaded_result.errors[0].source_name == "test_source"
    assert loaded_result.errors[0].error_type == "NetworkError"


def test_save_multiple_results(history_storage, sample_result):
    """Verify that multiple results are saved in order (most recent first)."""
    # Create 3 results with different timestamps
    result1 = sample_result
    result2 = AcquisitionResult(
        timestamp=datetime(2026, 8, 22, 11, 0, 0),
        total_sources=3,
        successful_sources=3,
        failed_sources=0,
        total_articles=15,
        execution_time=2.0,
        errors=[],
    )
    result3 = AcquisitionResult(
        timestamp=datetime(2026, 8, 22, 12, 0, 0),
        total_sources=7,
        successful_sources=6,
        failed_sources=1,
        total_articles=40,
        execution_time=5.0,
        errors=[],
    )

    # Save in order
    history_storage.save_result(result1)
    history_storage.save_result(result2)
    history_storage.save_result(result3)

    # Load history
    history = history_storage.get_history()

    # Assertions (most recent first)
    assert len(history) == 3
    assert history[0].total_articles == 40  # result3 (most recent)
    assert history[1].total_articles == 15  # result2
    assert history[2].total_articles == 25  # result1 (oldest)


# --- Test Rolling Window ---


def test_rolling_window_keeps_10_results(history_storage, sample_result):
    """Verify that only the 10 most recent results are kept."""
    # Save 12 results
    for i in range(12):
        result = AcquisitionResult(
            timestamp=datetime(2026, 8, 22, i, 0, 0),
            total_sources=i,
            successful_sources=i,
            failed_sources=0,
            total_articles=i * 5,
            execution_time=float(i),
            errors=[],
        )
        history_storage.save_result(result)

    # Load history
    history = history_storage.get_history()

    # Assertions
    assert len(history) == 10  # Should keep only 10

    # Verify most recent results are kept (i=11, 10, 9, ..., 2)
    assert history[0].total_sources == 11  # Most recent
    assert history[9].total_sources == 2  # Oldest kept


# --- Test Corrupted File ---


def test_load_corrupted_file_returns_empty(history_storage, temp_history_file):
    """Verify that a corrupted history file is handled gracefully."""
    # Write invalid JSON to file
    temp_history_file.write_text("This is not valid JSON {", encoding="utf-8")

    # Load history
    history = history_storage.get_history()

    # Assertions
    assert len(history) == 0


def test_load_invalid_structure_returns_empty(history_storage, temp_history_file):
    """Verify that a file with invalid structure is handled gracefully."""
    # Write valid JSON but wrong structure
    temp_history_file.write_text('{"wrong_key": "value"}', encoding="utf-8")

    # Load history
    history = history_storage.get_history()

    # Assertions
    assert len(history) == 0


# --- Test Missing File ---


def test_load_missing_file_returns_empty(history_storage, temp_history_file):
    """Verify that a missing history file returns empty list."""
    # Ensure file doesn't exist
    assert not temp_history_file.exists()

    # Load history
    history = history_storage.get_history()

    # Assertions
    assert len(history) == 0


def test_save_creates_file_if_not_exists(history_storage, temp_history_file, sample_result):
    """Verify that saving creates the file if it doesn't exist."""
    # Ensure file doesn't exist
    assert not temp_history_file.exists()

    # Save result
    history_storage.save_result(sample_result)

    # Assertions
    assert temp_history_file.exists()

    # Verify content
    history = history_storage.get_history()
    assert len(history) == 1


# --- Test Singleton & Convenience Functions ---


@patch("app.storage.history._history_storage", None)
def test_get_history_storage_singleton():
    """Verify that get_history_storage returns the same instance."""
    storage1 = get_history_storage()
    storage2 = get_history_storage()

    assert storage1 is storage2


@patch("app.storage.history.get_history_storage")
def test_save_acquisition_result_convenience(mock_get_storage, sample_result):
    """Verify that save_acquisition_result calls the storage correctly."""
    mock_storage = MagicMock()
    mock_get_storage.return_value = mock_storage

    save_acquisition_result(sample_result)

    mock_storage.save_result.assert_called_once_with(sample_result)


# --- Test last_run timestamp ---


def test_last_run_timestamp_updated(history_storage, temp_history_file, sample_result):
    """Verify that last_run timestamp is updated in the JSON file."""
    # Save result
    history_storage.save_result(sample_result)

    # Read raw JSON
    with open(temp_history_file, encoding="utf-8") as f:
        data = json.load(f)

    # Assertions
    assert "last_run" in data
    assert data["last_run"] == sample_result.timestamp.isoformat()
