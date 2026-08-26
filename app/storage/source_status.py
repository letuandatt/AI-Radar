"""Storage for source status with atomic write support."""

import json
import os
import tempfile
from pathlib import Path

from app.core.logger import get_logger
from app.models.status import SourceStatus

logger = get_logger(__name__)

_STATUS_FILE_PATH = Path("data/source_status.json")


class SourceStatusStorage:
    """Manages persistent storage of source statuses using atomic writes.

    Atomic write ensures that the status file is never left in a corrupted
    state, even if the application crashes during a write operation.
    """

    def __init__(self, file_path: Path | None = None) -> None:
        self._file_path = file_path or _STATUS_FILE_PATH
        self._ensure_directory_exists()

    def _ensure_directory_exists(self) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_data(self) -> dict[str, dict]:
        if not self._file_path.exists():
            return {}
        try:
            with open(self._file_path, encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    logger.warning("Source status file has invalid structure, resetting")
                    return {}
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load source status file: %s", e)
            return {}

    def _save_data(self, data: dict[str, dict]) -> None:
        dir_path = self._file_path.parent
        tmp_name = None
        try:
            # 1. Write to a temporary file in the same directory
            with tempfile.NamedTemporaryFile(
                mode="w", dir=dir_path, delete=False, encoding="utf-8", suffix=".tmp"
            ) as tmp_file:
                json.dump(data, tmp_file, indent=2)
                tmp_name = tmp_file.name

            # 2. Atomically replace the target file with the temporary file
            os.replace(tmp_name, self._file_path)
        except OSError as e:
            logger.error("Failed to save source status file: %s", e)
            # Clean up the temporary file if the replace operation failed
            if tmp_name and os.path.exists(tmp_name):
                os.remove(tmp_name)
            raise

    def save_status(self, status: SourceStatus) -> None:
        data = self._load_data()
        # Use mode="json" to ensure datetime is serialized to ISO format string
        data[status.source_name] = status.model_dump(mode="json")
        self._save_data(data)

    def get_status(self, source_name: str) -> SourceStatus | None:
        data = self._load_data()
        if source_name in data:
            try:
                return SourceStatus.model_validate(data[source_name])
            except Exception as e:
                logger.warning("Failed to parse status for %s: %s", source_name, e)
                return None
        return None

    def get_all_statuses(self) -> list[SourceStatus]:
        data = self._load_data()
        statuses = []
        for name, status_data in data.items():
            try:
                statuses.append(SourceStatus.model_validate(status_data))
            except Exception as e:
                logger.warning("Failed to parse status for %s: %s", name, e)
        return statuses

    def remove_status(self, source_name: str) -> None:
        data = self._load_data()
        if source_name in data:
            del data[source_name]
            self._save_data(data)
