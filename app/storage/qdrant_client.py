from enum import Enum
from typing import TYPE_CHECKING

from app.config.settings import Settings
from app.core.exceptions import StartupError
from app.core.logger import get_logger

# Block này chỉ mypy đọc được, không ảnh hưởng runtime
if TYPE_CHECKING:
    from qdrant_client import QdrantClient

logger = get_logger(__name__)


class DatabaseState(str, Enum):
    """States a database connection can occupy."""

    CREATED = "created"
    INITIALIZED = "initialized"
    CLOSED = "closed"


class DatabaseStateError(RuntimeError):
    """Raised when a database operation is invalid for its current state."""


class QdrantConnection:
    """Owns Qdrant database initialization and connection state."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._state = DatabaseState.CREATED

        # FIX: Khai báo rõ kiểu dữ liệu cho mypy
        self._client: QdrantClient | None = None

    @property
    def state(self) -> DatabaseState:
        """Return the current database connection state."""
        return self._state

    def is_ready(self) -> bool:
        """Return whether the storage is fully initialized and ready for use."""
        return self._state is DatabaseState.INITIALIZED

    def get_client(self) -> "QdrantClient":
        """Return the underlying Qdrant client for controlled access.

        This method allows higher-level modules (e.g., vectorstores/) to
        interact with the database while ensuring the connection is valid.

        Raises:
            DatabaseStateError: If the connection is not in INITIALIZED state.
        """
        if self._state is not DatabaseState.INITIALIZED:
            raise DatabaseStateError(
                f"Cannot get client from '{self._state.value}' state. "
                "Connection must be initialized first."
            )

        # State check guarantees _client is not None
        assert self._client is not None, "Client must exist when state is INITIALIZED"
        return self._client

    def initialize(self) -> None:
        """Initialize the Qdrant client and verify the connection."""
        if self._state is not DatabaseState.CREATED:
            raise DatabaseStateError(f"Cannot initialize database from {self._state.value} state.")

        logger.info("Qdrant database initialization started")

        try:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(
                url=self._settings.qdrant_url,
                api_key=self._settings.qdrant_api_key,
            )

            self._client.get_collections()

        except Exception as error:
            raise StartupError(f"Failed to initialize Qdrant database: {error}") from error

        self._state = DatabaseState.INITIALIZED
        logger.info("Qdrant database initialized successfully")

    def close(self) -> None:
        """Close the Qdrant client and release network resources."""
        if self._state is DatabaseState.CLOSED:
            return

        if self._state is not DatabaseState.INITIALIZED:
            raise DatabaseStateError(f"Cannot close database from {self._state.value} state.")

        if self._client:
            try:
                self._client.close()
            except Exception as error:
                # Log lỗi nhưng KHÔNG ném ra ngoài.
                # Điều này đảm bảo application shutdown không bị crash
                # chỉ vì một lỗi network khi đóng connection.
                logger.error("Failed to close Qdrant client gracefully: %s", error)

        self._state = DatabaseState.CLOSED
        logger.info("Qdrant database connection closed")
