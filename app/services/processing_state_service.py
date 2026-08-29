"""Service layer for processing state management.

Provides high-level operations for tracking and querying item
processing states, including checkpoint lookup, state updates,
and failed item retrieval for replay.
"""

from datetime import datetime, timezone

from app.core.logger import get_logger
from app.models.processing_state import ItemState, ProcessingState
from app.storage.processing_state import ProcessingStateStorage

logger = get_logger(__name__)


class ProcessingStateService:
    """Manages item-level processing state with checkpoint support.

    This service wraps the ProcessingStateStorage and provides
    business logic for:
    - Querying item status by content_hash
    - Updating item status after each pipeline stage
    - Retrieving failed items for replay
    - Clearing all state for full re-processing

    Thread Safety:
        Not thread-safe. Callers are responsible for synchronization
        if concurrent access is required.

    Example:
        service = ProcessingStateService(storage)
        status = service.get_status("abc123hash")
        if status and status.status == "success":
        ... # Skip this item
        ... pass
    """

    def __init__(self, storage: ProcessingStateStorage) -> None:
        """Initialize the service with its storage backend.

        Args:
            storage: The processing state storage implementation.
        """
        self._storage = storage
        self._state: ProcessingState = storage.load()

    @property
    def state(self) -> ProcessingState:
        """Return the current in-memory processing state."""
        return self._state

    def get_status(self, content_hash: str) -> ItemState | None:
        """Get the processing state for a specific item.

        Args:
            content_hash: The content hash identifying the item.

        Returns:
            The ItemState if found, None otherwise.
        """
        return self._state.items.get(content_hash)

    def update_status(
        self,
        content_hash: str,
        stage: str,
        status: str,
        error_type: str | None = None,
        error_message: str | None = None,
        processor_version: str = "1.0.0",
    ) -> None:
        """Update the processing state for an item.

        If the item already exists, its attempt_count is incremented
        and fields are updated. If it does not exist, a new entry
        is created.

        Args:
            content_hash: The content hash identifying the item.
            stage: The stage that was just completed or failed.
            status: "success" or "failed".
            error_type: Type of error (only for failed status).
            error_message: Error description (only for failed status).
            processor_version: Version of the processing pipeline.
        """
        existing = self._state.items.get(content_hash)

        if existing is not None:
            new_attempt_count = existing.attempt_count + 1
        else:
            new_attempt_count = 1

        item_state = ItemState(
            content_hash=content_hash,
            stage=stage,
            status=status,
            error_type=error_type,
            error_message=error_message,
            attempt_count=new_attempt_count,
            processor_version=processor_version,
            updated_at=datetime.now(timezone.utc),
        )

        self._state.items[content_hash] = item_state
        self._state.last_run = datetime.now(timezone.utc)

        logger.debug(
            "Updated state for %s: stage=%s, status=%s, attempt=%d",
            content_hash[:16],
            stage,
            status,
            new_attempt_count,
        )

    def get_failed_items(self) -> list[ItemState]:
        """Get all items that have a failed status.

        Returns:
            List of ItemState objects with status == "failed".
        """
        failed = [item for item in self._state.items.values() if item.status == "failed"]
        logger.debug("Found %d failed items", len(failed))
        return failed

    def clear_state(self) -> None:
        """Clear all processing state for a full re-process from scratch."""
        item_count = len(self._state.items)
        self._state = ProcessingState()
        self._persist()
        logger.info(
            "Cleared processing state: removed %d tracked items",
            item_count,
        )

    def flush(self) -> None:
        """Persist the current in-memory state to storage."""
        self._persist()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Write the current state to the storage backend."""
        self._storage.save(self._state)
