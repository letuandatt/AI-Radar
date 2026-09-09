"""Repository Initializer.

Orchestrates the initialization of all Knowledge Repository components:
SQLite, Qdrant, BM25, and Embedding Provider.

Implements simple schema version check.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.logger import get_logger
from app.services.embedding.factory import EmbeddingProviderFactory
from app.services.embedding.provider import EmbeddingProvider
from app.services.repository.config import RepositoryConfig
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from app.storage.search.bm25_index import BM25Index
from app.storage.vector.index_config import VectorIndexConfig
from app.storage.vector.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)

# Simple schema version
SCHEMA_VERSION = "1.0.0"


# =============================================================================
# Data Models
# =============================================================================


@dataclass(frozen=True)
class ComponentStatus:
    """Status of a single repository component.

    Attributes:
        name: Component name (e.g., "sqlite", "qdrant").
        available: Whether the component is available.
        message: Optional status message.
    """

    name: str
    available: bool
    message: str = ""


@dataclass(frozen=True)
class RepositoryState:
    """Snapshot of the repository state after initialization.

    Attributes:
        schema_version: Current schema version.
        sqlite_count: Number of KnowledgeObjects in SQLite.
        qdrant_count: Number of vector points in Qdrant.
        bm25_count: Number of documents in BM25 index.
        initialized_at: Timestamp of initialization.
        components: Status of each component.
    """

    schema_version: str
    sqlite_count: int
    qdrant_count: int
    bm25_count: int
    initialized_at: datetime
    components: list[ComponentStatus] = field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        """True if all components are available."""
        return all(c.available for c in self.components)


@dataclass(frozen=True)
class ValidationError:
    """A configuration validation error.

    Attributes:
        component: Component that failed validation.
        message: Error description.
        severity: "critical" or "warning".
    """

    component: str
    message: str
    severity: str = "critical"


# =============================================================================
# Exceptions
# =============================================================================


class RepositoryInitializationError(Exception):
    """Raised when repository initialization fails."""

    pass


class RepositoryNotInitializedError(Exception):
    """Raised when accessing components before initialization."""

    pass


# =============================================================================
# Repository Initializer
# =============================================================================


class RepositoryInitializer:
    """Orchestrates initialization of all Knowledge Repository components.

    Usage:
        config = RepositoryConfig()
        initializer = RepositoryInitializer(config)
        state = initializer.initialize()

        # Access created components
        sqlite_store = initializer.sqlite_store
        qdrant_store = initializer.qdrant_store

    Args:
        config: Repository configuration.
    """

    def __init__(self, config: RepositoryConfig) -> None:
        self._config = config
        self._sqlite_store: SQLiteKnowledgeStore | None = None
        self._qdrant_store: QdrantVectorStore | None = None
        self._bm25_index: BM25Index | None = None
        self._embedding_provider: EmbeddingProvider | None = None
        self._initialized = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> RepositoryConfig:
        """Return the repository configuration."""
        return self._config

    @property
    def sqlite_store(self) -> SQLiteKnowledgeStore:
        """Return the SQLite store. Raises if not initialized."""
        if self._sqlite_store is None:
            raise RepositoryNotInitializedError(
                "SQLite store not available. Call initialize() first."
            )
        return self._sqlite_store

    @property
    def qdrant_store(self) -> QdrantVectorStore:
        """Return the Qdrant store. Raises if not initialized."""
        if self._qdrant_store is None:
            raise RepositoryNotInitializedError(
                "Qdrant store not available. Call initialize() first."
            )
        return self._qdrant_store

    @property
    def bm25_index(self) -> BM25Index:
        """Return the BM25 index. Raises if not initialized."""
        if self._bm25_index is None:
            raise RepositoryNotInitializedError(
                "BM25 index not available. Call initialize() first."
            )
        return self._bm25_index

    @property
    def embedding_provider(self) -> EmbeddingProvider:
        """Return the embedding provider. Raises if not initialized."""
        if self._embedding_provider is None:
            raise RepositoryNotInitializedError(
                "Embedding provider not available. Call initialize() first."
            )
        return self._embedding_provider

    # ------------------------------------------------------------------
    # Main Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> RepositoryState:
        """Initialize all repository components.

        Steps:
        1. Validate configuration
        2. Initialize SQLite store + schema version check
        3. Initialize Qdrant store
        4. Initialize BM25 index
        5. Initialize embedding provider
        6. Return repository state

        Returns:
            RepositoryState with component statuses and counts.

        Raises:
            RepositoryInitializationError: If a critical component fails.
        """
        logger.info("Starting repository initialization")

        # Step 1: Validate config
        errors = self.validate_config()
        critical_errors = [e for e in errors if e.severity == "critical"]
        if critical_errors:
            messages = "; ".join(f"{e.component}: {e.message}" for e in critical_errors)
            raise RepositoryInitializationError(f"Configuration validation failed: {messages}")

        components: list[ComponentStatus] = []

        # Step 2: Initialize SQLite
        try:
            self._sqlite_store = self._init_sqlite()
            components.append(
                ComponentStatus(
                    name="sqlite",
                    available=True,
                    message=f"count={self._sqlite_store.count()}",
                )
            )
        except Exception as e:
            logger.error("Failed to initialize SQLite: %s", e)
            raise RepositoryInitializationError(f"SQLite initialization failed: {e}") from e

        # Step 3: Initialize Qdrant
        try:
            self._qdrant_store = self._init_qdrant()
            components.append(
                ComponentStatus(
                    name="qdrant",
                    available=True,
                    message=f"count={self._qdrant_store.count()}",
                )
            )
        except Exception as e:
            logger.error("Failed to initialize Qdrant: %s", e)
            raise RepositoryInitializationError(f"Qdrant initialization failed: {e}") from e

        # Step 4: Initialize BM25
        try:
            self._bm25_index = self._init_bm25()
            components.append(
                ComponentStatus(
                    name="bm25",
                    available=True,
                    message=f"count={self._bm25_index.document_count}",
                )
            )
        except Exception as e:
            logger.error("Failed to initialize BM25: %s", e)
            raise RepositoryInitializationError(f"BM25 initialization failed: {e}") from e

        # Step 5: Initialize Embedding Provider
        try:
            self._embedding_provider = self._init_embedding_provider()
            components.append(
                ComponentStatus(
                    name="embedding",
                    available=True,
                    message=f"provider={self._config.embedding_provider_type}",
                )
            )
        except Exception as e:
            logger.error("Failed to initialize embedding provider: %s", e)
            raise RepositoryInitializationError(
                f"Embedding provider initialization failed: {e}"
            ) from e

        self._initialized = True

        # Build state
        state = RepositoryState(
            schema_version=SCHEMA_VERSION,
            sqlite_count=self._sqlite_store.count(),
            qdrant_count=self._qdrant_store.count(),
            bm25_count=self._bm25_index.document_count,
            initialized_at=datetime.now(timezone.utc),
            components=components,
        )

        logger.info(
            "Repository initialized: sqlite=%d, qdrant=%d, bm25=%d, healthy=%s",
            state.sqlite_count,
            state.qdrant_count,
            state.bm25_count,
            state.is_healthy,
        )

        return state

    def shutdown(self) -> None:
        """Gracefully shutdown all initialized components."""
        if self._sqlite_store is not None:
            try:
                self._sqlite_store.close()
            except Exception as error:
                logger.error("Error closing SQLite store: %s", error)

        if self._qdrant_store is not None:
            try:
                self._qdrant_store.close()
            except Exception as error:
                logger.error("Error closing vector store: %s", error)

        logger.info("Knowledge Repository shutdown complete")

    # ------------------------------------------------------------------
    # Config Validation
    # ------------------------------------------------------------------

    def validate_config(self) -> list[ValidationError]:
        """Validate repository configuration.

        Checks:
        - SQLite path is writable
        - Qdrant is reachable
        - Embedding provider is accessible
        - BM25 index path is writable

        Returns:
            List of validation errors (empty if all valid).
        """
        errors: list[ValidationError] = []

        # Check SQLite path
        sqlite_dir = self._config.sqlite_path.parent
        if not sqlite_dir.exists():
            try:
                sqlite_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                errors.append(
                    ValidationError(
                        component="sqlite",
                        message=f"Cannot create directory {sqlite_dir}: {e}",
                        severity="critical",
                    )
                )
        elif not sqlite_dir.is_dir():
            errors.append(
                ValidationError(
                    component="sqlite",
                    message=f"Path {sqlite_dir} is not a directory",
                    severity="critical",
                )
            )

        # Check Qdrant reachable
        try:
            import httpx

            response = httpx.get(
                f"{self._config.qdrant_url}/collections",
                timeout=5.0,
            )
            if response.status_code != 200:
                errors.append(
                    ValidationError(
                        component="qdrant",
                        message=f"Qdrant returned status {response.status_code}",
                        severity="critical",
                    )
                )
        except Exception as e:
            errors.append(
                ValidationError(
                    component="qdrant",
                    message=f"Qdrant unreachable at {self._config.qdrant_url}: {e}",
                    severity="critical",
                )
            )

        # Check embedding provider
        if self._config.embedding_provider_type == "cohere":
            if not self._config.cohere_api_key:
                errors.append(
                    ValidationError(
                        component="embedding",
                        message="Cohere API key not configured",
                        severity="critical",
                    )
                )
        elif self._config.embedding_provider_type == "ollama":
            try:
                import httpx

                response = httpx.get(
                    f"{self._config.ollama_base_url}/api/tags",
                    timeout=5.0,
                )
                if response.status_code != 200:
                    errors.append(
                        ValidationError(
                            component="embedding",
                            message=f"Ollama returned status {response.status_code}",
                            severity="warning",
                        )
                    )
            except Exception as e:
                errors.append(
                    ValidationError(
                        component="embedding",
                        message=f"Ollama unreachable at {self._config.ollama_base_url}: {e}",
                        severity="warning",
                    )
                )
        else:
            errors.append(
                ValidationError(
                    component="embedding",
                    message=f"Unknown provider type: {self._config.embedding_provider_type}",
                    severity="critical",
                )
            )

        # Check BM25 index path
        bm25_dir = self._config.bm25_index_path.parent
        if not bm25_dir.exists():
            try:
                bm25_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                errors.append(
                    ValidationError(
                        component="bm25",
                        message=f"Cannot create directory {bm25_dir}: {e}",
                        severity="critical",
                    )
                )

        return errors

    # ------------------------------------------------------------------
    # Component Initialization
    # ------------------------------------------------------------------

    def _init_sqlite(self) -> SQLiteKnowledgeStore:
        """Initialize SQLite store and check schema version."""
        store = SQLiteKnowledgeStore(db_path=self._config.sqlite_path)

        # Simple schema version check (GAP-007: Alembic deferred)
        self._check_schema_version(store)

        # Ensure metadata indexes exist
        store.ensure_metadata_indexes()

        return store

    def _init_qdrant(self) -> QdrantVectorStore:
        """Initialize Qdrant store."""
        index_config = self._config.vector_index_config or VectorIndexConfig()

        store = QdrantVectorStore(
            url=self._config.qdrant_url,
            collection_name=self._config.qdrant_collection,
            timeout=self._config.qdrant_timeout,
            index_config=index_config,
        )

        if self._config.auto_create_collections:
            # Determine dimensions from embedding provider config
            # Default to 768 for Ollama nomic-embed-text-v2-moe
            dimensions = 768
            if self._config.embedding_provider_type == "cohere":
                dimensions = 1024

            store.ensure_collection(dimensions=dimensions)

        return store

    def _init_bm25(self) -> BM25Index:
        """Initialize BM25 index (load existing or create new)."""
        index = BM25Index(index_path=self._config.bm25_index_path)

        if self._config.bm25_index_path.exists():
            index.load()
            logger.info(
                "Loaded existing BM25 index: %d documents",
                index.document_count,
            )
        else:
            logger.info("BM25 index file not found, starting with empty index")

        return index

    def _init_embedding_provider(self) -> EmbeddingProvider:
        """Initialize embedding provider using factory."""
        provider = EmbeddingProviderFactory.create(
            provider_name=self._config.embedding_provider_type,
            cohere_api_key=self._config.cohere_api_key,
            ollama_base_url=self._config.ollama_base_url,
        )

        logger.info(
            "Initialized embedding provider: %s (%s)",
            provider.get_model_name(),
            self._config.embedding_provider_type,
        )

        return provider

    # ------------------------------------------------------------------
    # Schema Version Check (GAP-007: Simple version, Alembic deferred)
    # ------------------------------------------------------------------

    def _check_schema_version(self, store: SQLiteKnowledgeStore) -> str:
        """Check and update schema version in SQLite.

        This is a simple version check. Full Alembic migration
        support is deferred to be implemented later.

        Args:
            store: SQLiteKnowledgeStore instance.

        Returns:
            Current schema version string.
        """
        conn = store.conn_manager.get_connection()

        # Create schema_version table if not exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version TEXT NOT NULL,
                applied_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.commit()

        # Read current version
        row = conn.execute(
            "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
        ).fetchone()

        if row is None:
            # First run - insert current version
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, now),
            )
            conn.commit()
            logger.info("Schema version initialized: %s", SCHEMA_VERSION)
            return SCHEMA_VERSION

        stored_version = row[0]

        if stored_version != SCHEMA_VERSION:
            logger.warning(
                "Schema version mismatch: stored=%s, expected=%s. "
                "Manual migration may be required. "
                "(Alembic support deferred - GAP-007)",
                stored_version,
                SCHEMA_VERSION,
            )

        return stored_version  # type: ignore[no-any-return]
