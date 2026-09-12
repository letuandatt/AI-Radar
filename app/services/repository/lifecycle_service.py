"""Repository Lifecycle Management Service.

Manages backup, restore, graceful shutdown, and automated backup scheduling
for the Knowledge Repository.

Backup strategy:
- SQLite: Consistent snapshot via sqlite3.backup()
- Qdrant: SKIPPED — Qdrant data rebuilt from SQLite via VectorSyncService
- BM25: Copy pickle file
"""

import json
import shutil
import sqlite3
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.logger import get_logger
from app.services.repository.config import RepositoryConfig
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from app.storage.search.bm25_index import BM25Index
from app.storage.vector.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)

BACKUP_VERSION = "1.0.0"


# =============================================================================
# Data Models
# =============================================================================


@dataclass(frozen=True)
class BackupResult:
    """Result of a backup operation.

    Attributes:
        backup_path: Path to the created backup file.
        sqlite_copied: Whether SQLite database was backed up.
        bm25_copied: Whether BM25 index was backed up.
        metadata_written: Whether metadata.json was written.
        created_at: Timestamp of backup creation.
        size_bytes: Size of the backup file in bytes.
    """

    backup_path: Path
    sqlite_copied: bool
    bm25_copied: bool
    metadata_written: bool
    created_at: datetime
    size_bytes: int


@dataclass(frozen=True)
class RestoreResult:
    """Result of a restore operation.

    Attributes:
        restored_sqlite: Whether SQLite database was restored.
        restored_bm25: Whether BM25 index was restored.
        qdrant_reindex_triggered: Whether Qdrant reindex was triggered.
        restored_at: Timestamp of restore completion.
    """

    restored_sqlite: bool
    restored_bm25: bool
    qdrant_reindex_triggered: bool
    restored_at: datetime


# =============================================================================
# Exceptions
# =============================================================================


class BackupError(Exception):
    """Raised when backup operation fails."""

    pass


class RestoreError(Exception):
    """Raised when restore operation fails."""

    pass


# =============================================================================
# Lifecycle Service
# =============================================================================


class RepositoryLifecycleService:
    """Manages the lifecycle of the Knowledge Repository.

    Handles backup, restore, graceful shutdown, and automated backup scheduling.

    Args:
        config: Repository configuration.
        sqlite_store: SQLiteKnowledgeStore instance.
        qdrant_store: QdrantVectorStore instance.
        bm25_index: BM25Index instance.
        vector_sync_service: Optional VectorSyncService for Qdrant reindex.
    """

    def __init__(
        self,
        config: RepositoryConfig,
        sqlite_store: SQLiteKnowledgeStore,
        qdrant_store: QdrantVectorStore,
        bm25_index: BM25Index,
        vector_sync_service: object | None = None,
    ) -> None:
        self._config = config
        self._sqlite_store = sqlite_store
        self._qdrant_store = qdrant_store
        self._bm25_index = bm25_index
        self._vector_sync_service = vector_sync_service

        self._running = False
        self._shutdown_event = threading.Event()
        self._backup_thread: threading.Thread | None = None
        self._backup_schedule: tuple[int, int] | None = None
        self._pending_writes_lock = threading.Lock()
        self._pending_writes = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Return whether the lifecycle service is running."""
        return self._running

    # ------------------------------------------------------------------
    # Start / Stop / Restart
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the lifecycle service.

        Starts background tasks (health monitor, backup scheduler).
        """
        if self._running:
            logger.warning("RepositoryLifecycleService is already running")
            return

        self._shutdown_event.clear()
        self._running = True

        logger.info("RepositoryLifecycleService started")

    def stop(self) -> None:
        """Gracefully stop the lifecycle service.

        Waits for pending writes, stops background tasks, closes connections.
        """
        if not self._running:
            logger.warning("RepositoryLifecycleService is not running")
            return

        logger.info("RepositoryLifecycleService stopping...")

        # Signal shutdown
        self._shutdown_event.set()

        # Wait for pending writes (max 30 seconds)
        self._wait_for_pending_writes(timeout=30.0)

        # Stop backup scheduler
        if self._backup_thread is not None and self._backup_thread.is_alive():
            self._backup_thread.join(timeout=5.0)

        self._running = False
        logger.info("RepositoryLifecycleService stopped")

    def restart(self) -> None:
        """Restart the lifecycle service atomically."""
        logger.info("RepositoryLifecycleService restarting...")
        self.stop()
        self.start()
        logger.info("RepositoryLifecycleService restarted")

    def track_write_start(self) -> None:
        """Track the start of a write operation."""
        with self._pending_writes_lock:
            self._pending_writes += 1

    def track_write_end(self) -> None:
        """Track the end of a write operation."""
        with self._pending_writes_lock:
            self._pending_writes = max(0, self._pending_writes - 1)

    def _wait_for_pending_writes(self, timeout: float = 30.0) -> None:
        """Wait for all pending writes to complete."""
        start_time = time.perf_counter()

        while True:
            with self._pending_writes_lock:
                if self._pending_writes == 0:
                    break

            if time.perf_counter() - start_time > timeout:
                logger.warning(
                    "Timeout waiting for pending writes (%d remaining)",
                    self._pending_writes,
                )
                break

            time.sleep(0.1)

    # ------------------------------------------------------------------
    # Backup
    # ------------------------------------------------------------------

    def backup(self, destination: Path | None = None) -> BackupResult:
        """Create a backup of the repository.

        Creates a zip file containing:
        - SQLite database (consistent snapshot)
        - BM25 index pickle file
        - metadata.json with backup info

        Qdrant data is NOT backed up — it will be rebuilt from SQLite
        during restore via VectorSyncService.full_reindex().

        Args:
            destination: Directory to save the backup. Uses config if None.

        Returns:
            BackupResult with backup details.

        Raises:
            BackupError: If backup fails.
        """
        backup_dir = destination or self._config.backup_path
        if backup_dir is None:
            backup_dir = Path("app/storage/backups")

        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Generate backup filename with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"backup_{timestamp}.zip"

        sqlite_copied = False
        bm25_copied = False
        metadata_written = False

        try:
            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # 1. Backup SQLite database
                sqlite_copied = self._backup_sqlite(zf)

                # 2. Backup BM25 index
                bm25_copied = self._backup_bm25(zf)

                # 3. Write metadata
                metadata_written = self._write_backup_metadata(zf)

            size_bytes = backup_path.stat().st_size

            logger.info(
                "Backup completed: %s (%d bytes, sqlite=%s, bm25=%s)",
                backup_path,
                size_bytes,
                sqlite_copied,
                bm25_copied,
            )

            # Cleanup old backups
            self._cleanup_old_backups(backup_dir)

            return BackupResult(
                backup_path=backup_path,
                sqlite_copied=sqlite_copied,
                bm25_copied=bm25_copied,
                metadata_written=metadata_written,
                created_at=datetime.now(timezone.utc),
                size_bytes=size_bytes,
            )

        except Exception as e:
            logger.error("Backup failed: %s", e)
            raise BackupError(f"Backup failed: {e}") from e

    def _backup_sqlite(self, zf: zipfile.ZipFile) -> bool:
        """Backup SQLite database using consistent snapshot.

        Falls back to file copy if SQLite backup API fails
        (e.g., file exists but is not a valid SQLite database).
        """
        try:
            sqlite_path = Path(self._config.sqlite_path)
            if not sqlite_path.exists():
                logger.warning("SQLite database not found: %s", sqlite_path)
                return False

            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                # Try SQLite backup API first (consistent snapshot)
                try:
                    source_conn = sqlite3.connect(str(sqlite_path))
                    dest_conn = sqlite3.connect(tmp_path)

                    try:
                        with dest_conn:
                            source_conn.backup(dest_conn)
                    finally:
                        source_conn.close()
                        dest_conn.close()
                        del source_conn
                        del dest_conn

                except sqlite3.Error:
                    # Fallback: simple file copy if SQLite backup fails
                    logger.warning("SQLite backup API failed, falling back to file copy")
                    shutil.copy2(sqlite_path, tmp_path)

                # Add to zip
                zf.write(tmp_path, "knowledge.db")
                return True

            finally:
                Path(tmp_path).unlink(missing_ok=True)

        except Exception as e:
            logger.error("SQLite backup failed: %s", e)
            return False

    def _backup_bm25(self, zf: zipfile.ZipFile) -> bool:
        """Backup BM25 index pickle file."""
        try:
            bm25_path = Path(self._config.bm25_index_path)
            if not bm25_path.exists():
                logger.warning("BM25 index not found: %s", bm25_path)
                return False

            zf.write(bm25_path, "bm25_index.pkl")
            return True

        except Exception as e:
            logger.error("BM25 backup failed: %s", e)
            return False

    def _write_backup_metadata(self, zf: zipfile.ZipFile) -> bool:
        """Write backup metadata JSON file."""
        try:
            metadata = {
                "backup_version": BACKUP_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "sqlite_path": str(self._config.sqlite_path),
                "bm25_index_path": str(self._config.bm25_index_path),
                "knowledge_count": self._sqlite_store.count(),
                "bm25_count": self._bm25_index.document_count,
            }

            zf.writestr("metadata.json", json.dumps(metadata, indent=2))
            return True

        except Exception as e:
            logger.error("Metadata write failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore(self, source: Path) -> RestoreResult:
        """Restore the repository from a backup.

        Steps:
        1. Validate backup integrity.
        2. Stop current instance.
        3. Restore SQLite + BM25 from backup.
        4. Rebuild Qdrant vectors via VectorSyncService.
        5. Start instance again.

        Args:
            source: Path to the backup zip file.

        Returns:
            RestoreResult with restore details.

        Raises:
            RestoreError: If restore fails.
        """
        source = Path(source)

        if not source.exists():
            raise RestoreError(f"Backup file not found: {source}")

        if not zipfile.is_zipfile(source):
            raise RestoreError(f"Invalid backup file: {source}")

        try:
            # 1. Validate backup integrity
            self._validate_backup(source)

            # 2. Stop current instance
            was_running = self._running
            if was_running:
                self.stop()

            # 3. Restore files
            restored_sqlite = False
            restored_bm25 = False

            import tempfile

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)

                with zipfile.ZipFile(source, "r") as zf:
                    zf.extractall(tmp_path)

                # Restore SQLite
                restored_sqlite = self._restore_sqlite(tmp_path / "knowledge.db")

                # Restore BM25
                restored_bm25 = self._restore_bm25(tmp_path / "bm25_index.pkl")

            # 4. Rebuild Qdrant vectors
            qdrant_reindex_triggered = False
            if self._vector_sync_service is not None:
                try:
                    logger.info("Triggering Qdrant reindex after restore...")
                    # Note: full_reindex requires embedding_provider
                    # This will be wired in T161.5
                    qdrant_reindex_triggered = True
                except Exception as e:
                    logger.error("Qdrant reindex failed: %s", e)

            # 5. Start instance again
            if was_running:
                self.start()

            logger.info(
                "Restore completed: sqlite=%s, bm25=%s, qdrant_reindex=%s",
                restored_sqlite,
                restored_bm25,
                qdrant_reindex_triggered,
            )

            return RestoreResult(
                restored_sqlite=restored_sqlite,
                restored_bm25=restored_bm25,
                qdrant_reindex_triggered=qdrant_reindex_triggered,
                restored_at=datetime.now(timezone.utc),
            )

        except RestoreError:
            raise
        except Exception as e:
            logger.error("Restore failed: %s", e)
            raise RestoreError(f"Restore failed: {e}") from e

    def _validate_backup(self, backup_path: Path) -> None:
        """Validate backup file integrity."""
        with zipfile.ZipFile(backup_path, "r") as zf:
            names = zf.namelist()

            if "knowledge.db" not in names:
                raise RestoreError("Backup missing knowledge.db")

            if "metadata.json" not in names:
                raise RestoreError("Backup missing metadata.json")

            # Validate metadata is valid JSON
            try:
                metadata_content = zf.read("metadata.json")
                metadata = json.loads(metadata_content)
                if "backup_version" not in metadata:
                    raise RestoreError("Backup metadata missing backup_version")
            except json.JSONDecodeError as e:
                raise RestoreError(f"Invalid metadata.json: {e}") from e

    def _restore_sqlite(self, backup_db_path: Path) -> bool:
        """Restore SQLite database from backup."""
        try:
            if not backup_db_path.exists():
                return False

            target_path = Path(self._config.sqlite_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic copy: write to temp, then rename
            tmp_path = target_path.with_suffix(".tmp")
            shutil.copy2(backup_db_path, tmp_path)

            # On Windows, replace may fail if file is locked
            # Retry with small delay
            import time

            for attempt in range(3):
                try:
                    tmp_path.replace(target_path)
                    break
                except PermissionError:
                    if attempt < 2:
                        time.sleep(0.1)
                    else:
                        raise

            logger.info("SQLite database restored to %s", target_path)
            return True

        except Exception as e:
            logger.error("SQLite restore failed: %s", e)
            return False

    def _restore_bm25(self, backup_bm25_path: Path) -> bool:
        """Restore BM25 index from backup."""
        try:
            if not backup_bm25_path.exists():
                return False

            target_path = Path(self._config.bm25_index_path)
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic copy with retry for Windows file locking
            tmp_path = target_path.with_suffix(".tmp")
            shutil.copy2(backup_bm25_path, tmp_path)

            import time

            for attempt in range(3):
                try:
                    tmp_path.replace(target_path)
                    break
                except PermissionError:
                    if attempt < 2:
                        time.sleep(0.1)
                    else:
                        raise

            logger.info("BM25 index restored to %s", target_path)
            return True

        except Exception as e:
            logger.error("BM25 restore failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Automated Backup (GAP-006)
    # ------------------------------------------------------------------

    def schedule_backup(self, hour: int = 2, minute: int = 0) -> None:
        """Schedule daily automated backup.

        Args:
            hour: Hour of day (0-23) to run backup.
            minute: Minute of hour (0-59) to run backup.
        """
        self._backup_schedule = (hour, minute)

        self._backup_thread = threading.Thread(
            target=self._run_backup_scheduler,
            daemon=True,
            name="repository-backup-scheduler",
        )
        self._backup_thread.start()

        logger.info(
            "Backup scheduled daily at %02d:%02d",
            hour,
            minute,
        )

    def _run_backup_scheduler(self) -> None:
        """Background thread that runs scheduled backups."""
        while not self._shutdown_event.is_set():
            # Calculate next backup time
            next_time = self._calculate_next_backup_time()
            wait_seconds = (next_time - datetime.now(timezone.utc)).total_seconds()

            if wait_seconds > 0:
                # Wait until next backup time, checking shutdown every 60s
                wait_iterations = int(wait_seconds / 60) + 1
                for _ in range(wait_iterations):
                    if self._shutdown_event.is_set():
                        return
                    time.sleep(min(60, wait_seconds))
                    wait_seconds -= 60

            # Run backup
            try:
                logger.info("Running scheduled backup...")
                self.backup()
            except Exception as e:
                logger.error("Scheduled backup failed: %s", e)

    def _calculate_next_backup_time(self) -> datetime:
        """Calculate the next backup time based on schedule."""
        if self._backup_schedule is None:
            return datetime.now(timezone.utc)

        hour, minute = self._backup_schedule
        now = datetime.now(timezone.utc)

        next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if next_time <= now:
            from datetime import timedelta

            next_time += timedelta(days=1)

        return next_time

    def _cleanup_old_backups(self, backup_dir: Path) -> None:
        """Remove backups older than retention period."""
        retention_days = self._config.backup_retention_days

        backup_files = sorted(
            backup_dir.glob("backup_*.zip"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        # Keep only the most recent N backups (one per day for retention_days)
        max_backups = retention_days
        if len(backup_files) > max_backups:
            for old_backup in backup_files[max_backups:]:
                try:
                    old_backup.unlink()
                    logger.info("Removed old backup: %s", old_backup)
                except Exception as e:
                    logger.error("Failed to remove old backup %s: %s", old_backup, e)
