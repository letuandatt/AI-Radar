"""Unit tests for ProcessingHistoryStorage."""

from pathlib import Path

import pytest

from app.models.processing_result import ProcessingResult
from app.storage.processing_history import ProcessingHistoryStorage


@pytest.fixture
def history_path(tmp_path: Path) -> Path:
    """Provide a temporary file path for history storage."""
    return tmp_path / "processing_history.json"


@pytest.fixture
def storage(history_path: Path) -> ProcessingHistoryStorage:
    """Provide a ProcessingHistoryStorage instance."""
    return ProcessingHistoryStorage(file_path=history_path)


def _make_result(
    total_input: int = 10,
    objects_created: int = 8,
    failed_objects: int = 1,
) -> ProcessingResult:
    """Helper to create a ProcessingResult for testing."""
    return ProcessingResult(
        total_input=total_input,
        cleaned=total_input,
        normalized=total_input - failed_objects,
        extracted=total_input - failed_objects,
        objects_created=objects_created,
        objects_updated=0,
        failed_objects=failed_objects,
        skipped_objects=0,
        processing_duration=1.5,
        errors=[],
    )


# ==============================================================================
# Basic Operations Tests
# ==============================================================================


class TestBasicOperations:
    """Tests for basic append and retrieve operations."""

    def test_empty_storage_count(self, storage: ProcessingHistoryStorage) -> None:
        assert storage.count() == 0
        assert storage.get_all() == []

    def test_append_returns_run_id(self, storage: ProcessingHistoryStorage) -> None:
        result = _make_result()
        run_id = storage.append(result)

        assert run_id is not None
        assert isinstance(run_id, str)
        assert len(run_id) == 36  # UUID format

    def test_append_increments_count(self, storage: ProcessingHistoryStorage) -> None:
        storage.append(_make_result())
        assert storage.count() == 1

        storage.append(_make_result(total_input=20))
        assert storage.count() == 2

    def test_get_all_returns_chronological_order(self, storage: ProcessingHistoryStorage) -> None:
        storage.append(_make_result(total_input=10))
        storage.append(_make_result(total_input=20))
        storage.append(_make_result(total_input=30))

        entries = storage.get_all()
        assert len(entries) == 3
        assert entries[0].result.total_input == 10
        assert entries[1].result.total_input == 20
        assert entries[2].result.total_input == 30


# ==============================================================================
# Retrieval Tests
# ==============================================================================


class TestRetrieval:
    """Tests for get_latest and get_by_run_id."""

    def test_get_latest_empty_returns_none(self, storage: ProcessingHistoryStorage) -> None:
        assert storage.get_latest() is None

    def test_get_latest_returns_most_recent(self, storage: ProcessingHistoryStorage) -> None:
        storage.append(_make_result(total_input=10))
        storage.append(_make_result(total_input=20))
        storage.append(_make_result(total_input=30))

        latest = storage.get_latest()
        assert latest is not None
        assert latest.result.total_input == 30

    def test_get_by_run_id_found(self, storage: ProcessingHistoryStorage) -> None:
        run_id_1 = storage.append(_make_result(total_input=10))
        run_id_2 = storage.append(_make_result(total_input=20))

        entry = storage.get_by_run_id(run_id_1)
        assert entry is not None
        assert entry.result.total_input == 10

        entry = storage.get_by_run_id(run_id_2)
        assert entry is not None
        assert entry.result.total_input == 20

    def test_get_by_run_id_not_found(self, storage: ProcessingHistoryStorage) -> None:
        storage.append(_make_result())
        result = storage.get_by_run_id("nonexistent_run_id")
        assert result is None


# ==============================================================================
# Persistence Tests
# ==============================================================================


class TestPersistence:
    """Tests for file persistence and data durability."""

    def test_persist_and_reload(self, history_path: Path) -> None:
        """Entries survive storage recreation from the same file."""
        storage1 = ProcessingHistoryStorage(file_path=history_path)
        storage1.append(_make_result(total_input=10))
        storage1.append(_make_result(total_input=20))

        # Create a new instance pointing to the same file
        storage2 = ProcessingHistoryStorage(file_path=history_path)
        assert storage2.count() == 2

        entries = storage2.get_all()
        assert entries[0].result.total_input == 10
        assert entries[1].result.total_input == 20

    def test_empty_file_handling(self, history_path: Path) -> None:
        """Storage handles empty file gracefully."""
        history_path.write_text("", encoding="utf-8")
        storage = ProcessingHistoryStorage(file_path=history_path)
        assert storage.count() == 0

    def test_corrupted_file_handling(self, history_path: Path) -> None:
        """Storage handles corrupted JSON gracefully."""
        history_path.write_text("{invalid json!!!", encoding="utf-8")
        storage = ProcessingHistoryStorage(file_path=history_path)
        assert storage.count() == 0

    def test_missing_file_handling(self, tmp_path: Path) -> None:
        """Storage handles missing file gracefully."""
        missing_path = tmp_path / "nonexistent" / "history.json"
        storage = ProcessingHistoryStorage(file_path=missing_path)
        assert storage.count() == 0

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Append creates parent directories if they don't exist."""
        nested_path = tmp_path / "deep" / "nested" / "history.json"
        storage = ProcessingHistoryStorage(file_path=nested_path)
        storage.append(_make_result())

        assert nested_path.exists()

    def test_atomic_write_no_tmp_leftover(self, history_path: Path) -> None:
        """After append, no .tmp file should remain."""
        storage = ProcessingHistoryStorage(file_path=history_path)
        storage.append(_make_result())

        assert history_path.exists()
        tmp_path = history_path.with_suffix(".tmp")
        assert not tmp_path.exists()


# ==============================================================================
# Clear Tests
# ==============================================================================


class TestClear:
    """Tests for the clear operation."""

    def test_clear_removes_all_entries(self, storage: ProcessingHistoryStorage) -> None:
        storage.append(_make_result())
        storage.append(_make_result())
        storage.append(_make_result())

        assert storage.count() == 3

        storage.clear()

        assert storage.count() == 0
        assert storage.get_all() == []
        assert storage.get_latest() is None

    def test_clear_empty_storage_no_error(self, storage: ProcessingHistoryStorage) -> None:
        """Clearing an already-empty storage should not raise."""
        storage.clear()
        assert storage.count() == 0

    def test_clear_persists_empty_state(self, history_path: Path) -> None:
        """After clear, reloading from file should yield empty history."""
        storage1 = ProcessingHistoryStorage(file_path=history_path)
        storage1.append(_make_result())
        storage1.clear()

        storage2 = ProcessingHistoryStorage(file_path=history_path)
        assert storage2.count() == 0


# ==============================================================================
# Entry Metadata Tests
# ==============================================================================


class TestEntryMetadata:
    """Tests for ProcessingHistoryEntry metadata fields."""

    def test_entry_has_unique_run_ids(self, storage: ProcessingHistoryStorage) -> None:
        run_id_1 = storage.append(_make_result())
        run_id_2 = storage.append(_make_result())
        run_id_3 = storage.append(_make_result())

        assert run_id_1 != run_id_2
        assert run_id_2 != run_id_3
        assert run_id_1 != run_id_3

    def test_entry_has_completed_at_timestamp(self, storage: ProcessingHistoryStorage) -> None:
        storage.append(_make_result())
        entry = storage.get_latest()

        assert entry is not None
        assert entry.completed_at is not None

    def test_entry_preserves_result_data(self, storage: ProcessingHistoryStorage) -> None:
        """All ProcessingResult fields are preserved in the entry."""
        result = ProcessingResult(
            total_input=50,
            cleaned=50,
            normalized=48,
            extracted=45,
            objects_created=40,
            objects_updated=5,
            failed_objects=2,
            skipped_objects=3,
            processing_duration=12.7,
            errors=[{"stage": "extracted", "error_message": "timeout"}],
        )

        storage.append(result)
        entry = storage.get_latest()

        assert entry is not None
        assert entry.result.total_input == 50
        assert entry.result.cleaned == 50
        assert entry.result.normalized == 48
        assert entry.result.extracted == 45
        assert entry.result.objects_created == 40
        assert entry.result.objects_updated == 5
        assert entry.result.failed_objects == 2
        assert entry.result.skipped_objects == 3
        assert entry.result.processing_duration == 12.7
        assert len(entry.result.errors) == 1
