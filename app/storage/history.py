"""History storage for acquisition pipeline results.

This module provides persistent storage for tracking acquisition pipeline
execution history, maintaining a rolling window of recent results.
"""

import json
from datetime import datetime
from pathlib import Path

from app.core.logger import get_logger
from app.models.result import AcquisitionResult

logger = get_logger(__name__)

# Default path for history file
_HISTORY_FILE_PATH = Path("data/history.json")

# Maximum number of results to keep in history
_MAX_HISTORY_SIZE = 10


class HistoryStorage:
    """Manages persistent storage of acquisition pipeline results.

    Maintains a rolling window of the most recent acquisition results,
    stored in a JSON file for easy inspection and debugging.
    """

    def __init__(self, file_path: Path | None = None) -> None:
        """Initialize history storage.

        Args:
            file_path: Path to the history file. Defaults to data/history.json.
        """
        self._file_path = file_path or _HISTORY_FILE_PATH
        self._ensure_directory_exists()

    def _ensure_directory_exists(self) -> None:
        """Ensure the directory for the history file exists."""
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def save_result(self, result: AcquisitionResult) -> None:
        """Save an acquisition result to history.

        Maintains a rolling window of the most recent results.

        Args:
            result: The acquisition result to save.
        """
        history = self._load_history()

        # Add new result to the beginning (most recent first)
        history["results"].insert(0, result.to_dict())

        # Keep only the most recent results (rolling window)
        if len(history["results"]) > _MAX_HISTORY_SIZE:
            history["results"] = history["results"][:_MAX_HISTORY_SIZE]

        # Update last_run timestamp
        history["last_run"] = result.timestamp.isoformat()

        # Write to file
        self._write_history(history)

        logger.info(
            "Saved acquisition result to history: %d sources, %d articles",
            result.total_sources,
            result.total_articles,
        )

    def get_history(self) -> list[AcquisitionResult]:
        """Retrieve the acquisition history.

        Returns:
            List of AcquisitionResult objects, most recent first.
            Returns empty list if history file doesn't exist or is invalid.
        """
        history = self._load_history()
        results = []

        for result_dict in history.get("results", []):
            try:
                result = self._dict_to_result(result_dict)
                results.append(result)
            except Exception as error:
                logger.warning("Failed to parse history result: %s", error)

        return results

    def _load_history(self) -> dict:
        """Load history from file.

        Returns:
            Dictionary with history data. Returns empty structure if file
            doesn't exist or is invalid.
        """
        if not self._file_path.exists():
            return {"last_run": None, "results": []}

        try:
            with open(self._file_path, encoding="utf-8") as f:
                data = json.load(f)

                # Validate structure
                if not isinstance(data, dict):
                    logger.warning("History file has invalid structure, resetting")
                    return {"last_run": None, "results": []}

                # Ensure required keys exist
                if "last_run" not in data:
                    data["last_run"] = None
                if "results" not in data or not isinstance(data["results"], list):
                    data["results"] = []

                return data

        except json.JSONDecodeError as error:
            logger.error("Failed to parse history file: %s", error)
            return {"last_run": None, "results": []}
        except Exception as error:
            logger.error("Failed to load history file: %s", error)
            return {"last_run": None, "results": []}

    def _write_history(self, history: dict) -> None:
        """Write history to file.

        Args:
            history: Dictionary with history data.
        """
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception as error:
            logger.error("Failed to write history file: %s", error)
            raise

    def _dict_to_result(self, data: dict) -> AcquisitionResult:
        """Convert dictionary to AcquisitionResult.

        Args:
            data: Dictionary representation of AcquisitionResult.

        Returns:
            AcquisitionResult object.
        """
        from app.models.result import SourceError

        # Parse timestamp
        timestamp_str = data.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            timestamp = datetime.now()

        # Parse errors
        errors = []
        for error_dict in data.get("errors", []):
            error = SourceError(
                source_name=error_dict.get("source_name", ""),
                source_type=error_dict.get("source_type", ""),
                error_type=error_dict.get("error_type", ""),
                error_message=error_dict.get("error_message", ""),
            )
            errors.append(error)

        return AcquisitionResult(
            timestamp=timestamp,
            total_sources=data.get("total_sources", 0),
            successful_sources=data.get("successful_sources", 0),
            failed_sources=data.get("failed_sources", 0),
            total_articles=data.get("total_articles", 0),
            execution_time=data.get("execution_time", 0.0),
            errors=errors,
        )


# Module-level singleton instance
_history_storage: HistoryStorage | None = None


def get_history_storage() -> HistoryStorage:
    """Get the singleton HistoryStorage instance.

    Returns:
        HistoryStorage instance.
    """
    global _history_storage
    if _history_storage is None:
        _history_storage = HistoryStorage()
    return _history_storage


def save_acquisition_result(result: AcquisitionResult) -> None:
    """Save an acquisition result to history (convenience function).

    Args:
        result: The acquisition result to save.
    """
    get_history_storage().save_result(result)


def get_acquisition_history() -> list[AcquisitionResult]:
    """Get the acquisition history (convenience function).

    Returns:
        List of AcquisitionResult objects, most recent first.
    """
    return get_history_storage().get_history()
