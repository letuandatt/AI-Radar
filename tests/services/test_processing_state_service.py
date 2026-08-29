"""Unit tests for ProcessingStateService and ProcessingStateStorage."""

from datetime import datetime
from pathlib import Path

import pytest

from app.models.processing_state import ItemState, ProcessingState
from app.services.processing_state_service import ProcessingStateService
from app.storage.processing_state import ProcessingStateStorage


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    """Provide a temporary file path for state storage."""
    return tmp_path / "processing_state.json"


@pytest.fixture
def storage(state_path: Path) -> ProcessingStateStorage:
    """Provide a ProcessingStateStorage instance."""
    return ProcessingStateStorage(file_path=state_path)


@pytest.fixture
def service(storage: ProcessingStateStorage) -> ProcessingStateService:
    """Provide a ProcessingStateService instance."""
    return ProcessingStateService(storage=storage)


# ==============================================================================
# Storage Tests
# ==============================================================================


class TestProcessingStateStorage:
    """Tests for ProcessingStateStorage load/save operations."""

    def test_load_missing_file_returns_empty_state(self, storage: ProcessingStateStorage) -> None:
        """Missing file should return an empty ProcessingState."""
        state = storage.load()
        assert state.items == {}
        assert state.last_run is None

    def test_load_empty_file_returns_empty_state(
        self, storage: ProcessingStateStorage, state_path: Path
    ) -> None:
        """Empty file should return an empty ProcessingState."""
        state_path.write_text("", encoding="utf-8")
        state = storage.load()
        assert state.items == {}

    def test_load_corrupted_file_returns_empty_state(
        self, storage: ProcessingStateStorage, state_path: Path
    ) -> None:
        """Corrupted JSON should return an empty ProcessingState gracefully."""
        state_path.write_text("{invalid json!!!", encoding="utf-8")
        state = storage.load()
        assert state.items == {}

    def test_save_and_load_roundtrip(
        self, storage: ProcessingStateStorage, state_path: Path
    ) -> None:
        """State should survive a save/load cycle."""
        state = ProcessingState(
            items={
                "hash_a": ItemState(
                    content_hash="hash_a",
                    stage="normalized",
                    status="success",
                    attempt_count=1,
                ),
                "hash_b": ItemState(
                    content_hash="hash_b",
                    stage="extracted",
                    status="failed",
                    error_type="extraction_error",
                    error_message="LLM timeout",
                    attempt_count=2,
                ),
            },
            last_run=datetime(2025, 1, 1, 12, 0, 0),
        )

        storage.save(state)
        loaded = storage.load()

        assert len(loaded.items) == 2
        assert loaded.items["hash_a"].stage == "normalized"
        assert loaded.items["hash_a"].status == "success"
        assert loaded.items["hash_b"].status == "failed"
        assert loaded.items["hash_b"].error_message == "LLM timeout"
        assert loaded.items["hash_b"].attempt_count == 2

    def test_atomic_write_no_partial_file(
        self, storage: ProcessingStateStorage, state_path: Path
    ) -> None:
        """After save, only the target file should exist (no .tmp leftover)."""
        state = ProcessingState(
            items={"hash_x": ItemState(content_hash="hash_x", stage="cleaned", status="success")}
        )
        storage.save(state)

        assert state_path.exists()
        tmp_path = state_path.with_suffix(".tmp")
        assert not tmp_path.exists()

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        """Save should create parent directories if they don't exist."""
        nested_path = tmp_path / "deep" / "nested" / "state.json"
        nested_storage = ProcessingStateStorage(file_path=nested_path)
        state = ProcessingState(
            items={"hash_y": ItemState(content_hash="hash_y", stage="stored", status="success")}
        )
        nested_storage.save(state)
        assert nested_path.exists()


# ==============================================================================
# Service Tests
# ==============================================================================


class TestProcessingStateService:
    """Tests for ProcessingStateService business logic."""

    def test_get_status_nonexistent_returns_none(self, service: ProcessingStateService) -> None:
        result = service.get_status("nonexistent_hash")
        assert result is None

    def test_update_status_creates_new_item(self, service: ProcessingStateService) -> None:
        service.update_status("hash_a", "cleaned", "success")

        status = service.get_status("hash_a")
        assert status is not None
        assert status.content_hash == "hash_a"
        assert status.stage == "cleaned"
        assert status.status == "success"
        assert status.attempt_count == 1
        assert status.error_type is None
        assert status.error_message is None

    def test_update_status_increments_attempt_count(self, service: ProcessingStateService) -> None:
        """Retrying an item should increment attempt_count."""
        service.update_status("hash_a", "cleaned", "success")
        service.update_status(
            "hash_a", "normalized", "failed", error_type="timeout", error_message="Connection lost"
        )

        status = service.get_status("hash_a")
        assert status is not None
        assert status.attempt_count == 2
        assert status.status == "failed"
        assert status.stage == "normalized"
        assert status.error_type == "timeout"

    def test_update_status_multiple_retries(self, service: ProcessingStateService) -> None:
        """Multiple retries should keep incrementing attempt_count."""
        service.update_status("hash_a", "cleaned", "success")
        service.update_status("hash_a", "normalized", "failed")
        service.update_status("hash_a", "normalized", "failed")
        service.update_status("hash_a", "normalized", "success")

        status = service.get_status("hash_a")
        assert status is not None
        assert status.attempt_count == 4
        assert status.status == "success"
        assert status.stage == "normalized"

    def test_get_failed_items_empty_when_all_success(self, service: ProcessingStateService) -> None:
        service.update_status("hash_a", "stored", "success")
        service.update_status("hash_b", "stored", "success")

        failed = service.get_failed_items()
        assert failed == []

    def test_get_failed_items_returns_only_failed(self, service: ProcessingStateService) -> None:
        service.update_status("hash_a", "stored", "success")
        service.update_status(
            "hash_b", "extracted", "failed", error_type="llm_error", error_message="Rate limited"
        )
        service.update_status("hash_c", "normalized", "failed", error_type="validation_error")
        service.update_status("hash_d", "stored", "success")

        failed = service.get_failed_items()
        assert len(failed) == 2

        failed_hashes = {item.content_hash for item in failed}
        assert failed_hashes == {"hash_b", "hash_c"}

    def test_clear_state_removes_all_items(self, service: ProcessingStateService) -> None:
        service.update_status("hash_a", "cleaned", "success")
        service.update_status("hash_b", "normalized", "failed")

        assert service.get_status("hash_a") is not None

        service.clear_state()

        assert service.get_status("hash_a") is None
        assert service.get_status("hash_b") is None
        assert service.get_failed_items() == []
        assert service.state.items == {}

    def test_flush_persists_state(self, service: ProcessingStateService, state_path: Path) -> None:
        """flush() should write state to disk."""
        service.update_status("hash_a", "cleaned", "success")
        service.flush()

        assert state_path.exists()

        # Verify by loading from a new storage instance
        new_storage = ProcessingStateStorage(file_path=state_path)
        loaded = new_storage.load()
        assert "hash_a" in loaded.items
        assert loaded.items["hash_a"].stage == "cleaned"

    def test_state_survives_service_restart(self, state_path: Path) -> None:
        """State should persist across service instances (simulating restart)."""
        storage1 = ProcessingStateStorage(file_path=state_path)
        service1 = ProcessingStateService(storage=storage1)
        service1.update_status("hash_a", "stored", "success")
        service1.flush()

        # Simulate restart: create new service from same file
        storage2 = ProcessingStateStorage(file_path=state_path)
        service2 = ProcessingStateService(storage=storage2)

        status = service2.get_status("hash_a")
        assert status is not None
        assert status.stage == "stored"
        assert status.status == "success"

    def test_last_run_updated_on_status_change(self, service: ProcessingStateService) -> None:
        assert service.state.last_run is None

        service.update_status("hash_a", "cleaned", "success")
        assert service.state.last_run is not None
        assert isinstance(service.state.last_run, datetime)
