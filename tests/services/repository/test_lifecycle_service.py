"""Unit tests for RepositoryLifecycleService."""

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.repository.config import RepositoryConfig
from app.services.repository.lifecycle_service import (
    RepositoryLifecycleService,
    RestoreError,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def config(tmp_path: Path) -> RepositoryConfig:
    """Create a test RepositoryConfig with temp paths."""
    return RepositoryConfig(
        sqlite_path=tmp_path / "knowledge.db",
        qdrant_url="http://localhost:6333",
        qdrant_collection="test_collection",
        bm25_index_path=tmp_path / "bm25_index.pkl",
        backup_path=tmp_path / "backups",
        backup_retention_days=3,
    )


@pytest.fixture
def mock_sqlite_store():
    """Create a mock SQLiteKnowledgeStore."""
    store = MagicMock()
    store.count.return_value = 10
    return store


@pytest.fixture
def mock_qdrant_store():
    """Create a mock QdrantVectorStore."""
    store = MagicMock()
    store.count.return_value = 10
    return store


@pytest.fixture
def mock_bm25_index():
    """Create a mock BM25Index."""
    index = MagicMock()
    index.document_count = 10
    return index


@pytest.fixture
def lifecycle_service(config, mock_sqlite_store, mock_qdrant_store, mock_bm25_index):
    """Create a RepositoryLifecycleService with mocks."""
    return RepositoryLifecycleService(
        config=config,
        sqlite_store=mock_sqlite_store,
        qdrant_store=mock_qdrant_store,
        bm25_index=mock_bm25_index,
    )


# =============================================================================
# Start / Stop / Restart Tests
# =============================================================================


class TestStartStopRestart:
    """Tests for start, stop, and restart operations."""

    def test_start_sets_running_flag(self, lifecycle_service) -> None:
        """start() sets the running flag."""
        assert not lifecycle_service.is_running
        lifecycle_service.start()
        assert lifecycle_service.is_running

    def test_stop_clears_running_flag(self, lifecycle_service) -> None:
        """stop() clears the running flag."""
        lifecycle_service.start()
        assert lifecycle_service.is_running

        lifecycle_service.stop()
        assert not lifecycle_service.is_running

    def test_start_idempotent(self, lifecycle_service) -> None:
        """Calling start() twice does not fail."""
        lifecycle_service.start()
        lifecycle_service.start()
        assert lifecycle_service.is_running

    def test_stop_idempotent(self, lifecycle_service) -> None:
        """Calling stop() when not running does not fail."""
        lifecycle_service.stop()
        assert not lifecycle_service.is_running

    def test_restart_is_atomic(self, lifecycle_service) -> None:
        """restart() stops and starts atomically."""
        lifecycle_service.start()
        lifecycle_service.restart()
        assert lifecycle_service.is_running

    def test_stop_waits_for_pending_writes(self, lifecycle_service) -> None:
        """stop() waits for pending writes to complete."""
        lifecycle_service.start()

        # Simulate a pending write
        lifecycle_service.track_write_start()

        # Stop should not hang (timeout after 30s, but we'll end the write quickly)
        import threading

        def end_write():
            import time

            time.sleep(0.5)
            lifecycle_service.track_write_end()

        t = threading.Thread(target=end_write)
        t.start()

        lifecycle_service.stop()
        t.join()

        assert not lifecycle_service.is_running


# =============================================================================
# Backup Tests
# =============================================================================


class TestBackup:
    """Tests for backup operations."""

    def test_backup_creates_zip(self, lifecycle_service, config, tmp_path) -> None:
        """backup() creates a zip file."""
        # Create dummy files
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        config.sqlite_path.touch()
        config.bm25_index_path.parent.mkdir(parents=True, exist_ok=True)
        config.bm25_index_path.touch()

        result = lifecycle_service.backup()

        assert result.backup_path.exists()
        assert result.backup_path.suffix == ".zip"
        assert result.size_bytes > 0

    def test_backup_contains_all_files(self, lifecycle_service, config, tmp_path) -> None:
        """Backup zip contains SQLite, BM25, and metadata."""
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        config.sqlite_path.touch()
        config.bm25_index_path.parent.mkdir(parents=True, exist_ok=True)
        config.bm25_index_path.touch()

        result = lifecycle_service.backup()

        with zipfile.ZipFile(result.backup_path, "r") as zf:
            names = zf.namelist()

        assert "knowledge.db" in names
        assert "bm25_index.pkl" in names
        assert "metadata.json" in names

    def test_backup_contains_metadata(self, lifecycle_service, config, tmp_path) -> None:
        """Backup metadata.json contains required fields."""
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        config.sqlite_path.touch()
        config.bm25_index_path.parent.mkdir(parents=True, exist_ok=True)
        config.bm25_index_path.touch()

        result = lifecycle_service.backup()

        with zipfile.ZipFile(result.backup_path, "r") as zf:
            metadata_content = zf.read("metadata.json")
            metadata = json.loads(metadata_content)

        assert "backup_version" in metadata
        assert "created_at" in metadata
        assert "knowledge_count" in metadata
        assert metadata["backup_version"] == "1.0.0"

    def test_backup_result_fields(self, lifecycle_service, config, tmp_path) -> None:
        """BackupResult has correct fields."""
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        config.sqlite_path.touch()
        config.bm25_index_path.parent.mkdir(parents=True, exist_ok=True)
        config.bm25_index_path.touch()

        result = lifecycle_service.backup()

        assert result.sqlite_copied is True
        assert result.bm25_copied is True
        assert result.metadata_written is True
        assert result.created_at is not None

    def test_backup_handles_missing_files(self, lifecycle_service, config, tmp_path) -> None:
        """backup() handles missing files gracefully."""
        # Don't create any files
        result = lifecycle_service.backup()

        # Backup should still be created, but with missing files
        assert result.backup_path.exists()
        assert result.sqlite_copied is False
        assert result.bm25_copied is False


# =============================================================================
# Restore Tests
# =============================================================================


class TestRestore:
    """Tests for restore operations."""

    def test_restore_validates_integrity(self, lifecycle_service, tmp_path) -> None:
        """restore() raises RestoreError for invalid backup."""
        # Create a non-zip file
        invalid_backup = tmp_path / "invalid.zip"
        invalid_backup.write_text("not a zip file")

        with pytest.raises(RestoreError, match="Invalid backup"):
            lifecycle_service.restore(invalid_backup)

    def test_restore_validates_missing_db(self, lifecycle_service, tmp_path) -> None:
        """restore() raises RestoreError when knowledge.db is missing."""
        invalid_backup = tmp_path / "missing_db.zip"

        with zipfile.ZipFile(invalid_backup, "w") as zf:
            zf.writestr("metadata.json", '{"backup_version": "1.0.0"}')

        with pytest.raises(RestoreError, match="missing knowledge.db"):
            lifecycle_service.restore(invalid_backup)

    def test_restore_nonexistent_file(self, lifecycle_service, tmp_path) -> None:
        """restore() raises RestoreError for nonexistent file."""
        with pytest.raises(RestoreError, match="not found"):
            lifecycle_service.restore(tmp_path / "nonexistent.zip")

    def test_backup_then_restore(self, lifecycle_service, config, tmp_path) -> None:
        """Backup followed by restore preserves data."""
        import sqlite3

        # Create a VALID SQLite database (not just dummy bytes)
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.sqlite_path))
        conn.execute("CREATE TABLE knowledge_objects (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO knowledge_objects (id) VALUES ('test_item_001')")
        conn.commit()
        conn.close()

        # Create BM25 index file
        config.bm25_index_path.parent.mkdir(parents=True, exist_ok=True)
        config.bm25_index_path.write_bytes(b"bm25 data")

        # Backup
        backup_result = lifecycle_service.backup()

        assert backup_result.sqlite_copied is True
        assert backup_result.bm25_copied is True

        # Overwrite original files (simulate corruption)
        config.sqlite_path.write_bytes(b"corrupted data")
        config.bm25_index_path.write_bytes(b"corrupted bm25")

        # Restore
        restore_result = lifecycle_service.restore(backup_result.backup_path)

        assert restore_result.restored_sqlite is True
        assert restore_result.restored_bm25 is True

        # Verify restored SQLite is valid and contains data
        restored_conn = sqlite3.connect(str(config.sqlite_path))
        rows = restored_conn.execute("SELECT id FROM knowledge_objects").fetchall()
        restored_conn.close()

        assert len(rows) == 1
        assert rows[0][0] == "test_item_001"

        # Verify restored BM25
        assert config.bm25_index_path.read_bytes() == b"bm25 data"


# =============================================================================
# Cleanup Old Backups Tests
# =============================================================================


class TestCleanupOldBackups:
    """Tests for backup retention cleanup."""

    def test_cleanup_old_backups(self, lifecycle_service, config, tmp_path) -> None:
        """Cleanup removes backups beyond retention period."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Create 5 backup files
        for i in range(5):
            backup_file = backup_dir / f"backup_2025010{i}_100000.zip"
            backup_file.write_bytes(b"data")

        # Config has retention_days=3
        lifecycle_service._cleanup_old_backups(backup_dir)

        remaining = list(backup_dir.glob("backup_*.zip"))
        assert len(remaining) <= 3
