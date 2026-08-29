"""Storage layer for processing history persistence.

Implements append-only file-based persistence for pipeline run results,
enabling historical tracking of processing metrics over time.
Uses atomic write to prevent corruption during persistence.
"""

import json
import os
from pathlib import Path

from app.core.logger import get_logger
from app.models.processing_history import ProcessingHistoryEntry
from app.models.processing_result import ProcessingResult

logger = get_logger(__name__)


class ProcessingHistoryStorage:
    """Append-only file-based storage for processing history.

    Stores a chronological list of ProcessingHistoryEntry records
    in a JSON file. Each pipeline run appends a new entry.

    Attributes:
        file_path: Path to the JSON history file.
    """

    def __init__(self, file_path: str | Path) -> None:
        """Initialize the processing history storage.

        Args:
            file_path: Path to the JSON file for history persistence.
        """
        self._file_path = Path(file_path)
        self._entries: list[ProcessingHistoryEntry] = []
        self._load()

    @property
    def file_path(self) -> Path:
        """Return the storage file path."""
        return self._file_path

    def append(self, result: ProcessingResult) -> str:
        """Append a new processing result to the history.

        Creates a ProcessingHistoryEntry with a unique run_id
        and current timestamp, then persists to disk.

        Args:
            result: The processing result to record.

        Returns:
            The run_id of the newly created entry.
        """
        entry = ProcessingHistoryEntry(result=result)
        self._entries.append(entry)
        self._persist()

        logger.info(
            "Recorded processing history: run_id=%s, total_input=%d, created=%d, failed=%d",
            entry.run_id,
            result.total_input,
            result.objects_created,
            result.failed_objects,
        )

        return entry.run_id

    def get_all(self) -> list[ProcessingHistoryEntry]:
        """Retrieve all history entries in chronological order.

        Returns:
            List of all ProcessingHistoryEntry records.
        """
        return list(self._entries)

    def get_latest(self) -> ProcessingHistoryEntry | None:
        """Retrieve the most recent history entry.

        Returns:
            The latest ProcessingHistoryEntry, or None if history is empty.
        """
        if not self._entries:
            return None
        return self._entries[-1]

    def get_by_run_id(self, run_id: str) -> ProcessingHistoryEntry | None:
        """Retrieve a specific history entry by its run_id.

        Args:
            run_id: The unique identifier of the pipeline run.

        Returns:
            The matching ProcessingHistoryEntry, or None if not found.
        """
        for entry in self._entries:
            if entry.run_id == run_id:
                return entry
        return None

    def count(self) -> int:
        """Return the total number of history entries.

        Returns:
            Total entry count.
        """
        return len(self._entries)

    def clear(self) -> None:
        """Clear all history entries and persist the empty state."""
        entry_count = len(self._entries)
        self._entries = []
        self._persist()
        logger.info(
            "Cleared processing history: removed %d entries",
            entry_count,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load history entries from the JSON file into memory."""
        if not self._file_path.exists():
            logger.debug(
                "History file %s not found, starting with empty history",
                self._file_path,
            )
            return

        try:
            raw_data = self._file_path.read_text(encoding="utf-8")
            if not raw_data.strip():
                return

            records = json.loads(raw_data)
            for record in records:
                entry = ProcessingHistoryEntry.model_validate(record)
                self._entries.append(entry)

            logger.info(
                "Loaded %d processing history entries from %s",
                len(self._entries),
                self._file_path,
            )
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(
                "Failed to load processing history from %s: %s. Starting with empty history.",
                self._file_path,
                e,
            )

    def _persist(self) -> None:
        """Write all history entries to the JSON file using atomic write."""
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self._file_path.with_suffix(".tmp")
        records = [entry.model_dump(mode="json") for entry in self._entries]
        content = json.dumps(records, indent=2, ensure_ascii=False)

        try:
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(tmp_path, self._file_path)
            logger.debug(
                "Persisted %d processing history entries to %s",
                len(records),
                self._file_path,
            )
        except OSError as e:
            logger.error(
                "Failed to persist processing history to %s: %s",
                self._file_path,
                e,
            )
            raise
