"""SQLite base utilities: connection management.

Provides the foundational reliability patterns used by SQLiteKnowledgeStore.
"""

import sqlite3
import threading
from pathlib import Path

from app.core.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# SQLite Connection Manager
# =============================================================================


class SQLiteConnectionManager:
    """Manages SQLite connections with timeout and thread safety.

    Args:
        db_path: Path to the SQLite database file.
        timeout: Transaction timeout in seconds.
    """

    def __init__(self, db_path: str | Path, timeout: float = 30.0) -> None:
        self._db_path = Path(db_path)
        self._timeout = timeout
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def get_connection(self) -> sqlite3.Connection:
        """Get or create a SQLite connection.

        Returns:
            Active sqlite3.Connection.

        Raises:
            sqlite3.Error: If connection cannot be established.
        """
        with self._lock:
            if self._connection is None:
                # Ensure parent directory exists
                self._db_path.parent.mkdir(parents=True, exist_ok=True)
                self._connection = sqlite3.connect(
                    str(self._db_path),
                    timeout=self._timeout,
                    check_same_thread=False,
                )
                # Enable WAL mode for better concurrent read performance
                self._connection.execute("PRAGMA journal_mode=WAL")
                # Enable foreign keys
                self._connection.execute("PRAGMA foreign_keys=ON")
                logger.debug(
                    "SQLite connection established: %s (timeout=%.1fs)",
                    self._db_path,
                    self._timeout,
                )
            return self._connection

    def close(self) -> None:
        """Close the SQLite connection."""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
                logger.debug("SQLite connection closed: %s", self._db_path)
