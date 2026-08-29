"""Storage layer for processing state persistence.

Implements atomic file-based persistence for the processing state,
ensuring that state is never corrupted even if the process is
interrupted during a write operation.
"""

import json
import os
from pathlib import Path

from app.core.logger import get_logger
from app.models.processing_state import ProcessingState

logger = get_logger(__name__)


class ProcessingStateStorage:
    """Atomic file-based storage for processing state.

    Uses the atomic write pattern: data is written to a temporary file
    first, then atomically replaced onto the target path. This ensures
    the state file is never left in a partially-written state.

    Attributes:
        file_path: Path to the JSON state file.
    """

    def __init__(self, file_path: str | Path) -> None:
        """Initialize the processing state storage.

        Args:
            file_path: Path to the JSON file for state persistence.
        """
        self._file_path = Path(file_path)

    @property
    def file_path(self) -> Path:
        """Return the storage file path."""
        return self._file_path

    def load(self) -> ProcessingState:
        """Load processing state from the JSON file.

        Returns an empty state if the file does not exist or is corrupted.

        Returns:
            The loaded ProcessingState, or an empty state on failure.
        """
        if not self._file_path.exists():
            logger.debug(
                "State file %s not found, returning empty state",
                self._file_path,
            )
            return ProcessingState()

        try:
            raw_data = self._file_path.read_text(encoding="utf-8")
            if not raw_data.strip():
                return ProcessingState()

            data = json.loads(raw_data)
            state = ProcessingState.model_validate(data)
            logger.info(
                "Loaded processing state: %d items tracked",
                len(state.items),
            )
            return state

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(
                "Failed to load processing state from %s: %s. Returning empty state.",
                self._file_path,
                e,
            )
            return ProcessingState()

    def save(self, state: ProcessingState) -> None:
        """Persist processing state to the JSON file using atomic write.

        Writes to a temporary file first, then atomically replaces the
        target file to prevent corruption.

        Args:
            state: The processing state to persist.
        """
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self._file_path.with_suffix(".tmp")
        content = state.model_dump_json(indent=2)

        try:
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(tmp_path, self._file_path)
            logger.debug(
                "Persisted processing state (%d items) to %s",
                len(state.items),
                self._file_path,
            )
        except OSError as e:
            logger.error(
                "Failed to persist processing state to %s: %s",
                self._file_path,
                e,
            )
            raise
