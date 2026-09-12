"""Unit tests for RepositoryInitializer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.repository.config import RepositoryConfig
from app.services.repository.initializer import (
    ComponentStatus,
    RepositoryInitializationError,
    RepositoryInitializer,
    RepositoryNotInitializedError,
    RepositoryState,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def config(tmp_path: Path) -> RepositoryConfig:
    """Create a test RepositoryConfig with temp paths."""
    return RepositoryConfig(
        sqlite_path=tmp_path / "test_knowledge.db",
        qdrant_url="http://localhost:6333",
        qdrant_collection="test_collection",
        bm25_index_path=tmp_path / "bm25_index.pkl",
        embedding_provider_type="ollama",
        ollama_base_url="http://localhost:11434",
    )


@pytest.fixture
def initializer(config: RepositoryConfig) -> RepositoryInitializer:
    """Create a RepositoryInitializer with test config."""
    return RepositoryInitializer(config)


# =============================================================================
# Config Validation Tests
# =============================================================================


class TestValidateConfig:
    """Tests for validate_config method."""

    def test_validate_config_creates_directories(
        self, config: RepositoryConfig, tmp_path: Path
    ) -> None:
        """validate_config creates missing directories."""
        # Point to non-existent directories
        new_config = RepositoryConfig(
            sqlite_path=tmp_path / "new_dir" / "test.db",
            bm25_index_path=tmp_path / "new_dir2" / "bm25.pkl",
            qdrant_url=config.qdrant_url,
        )
        initializer = RepositoryInitializer(new_config)

        # Mock Qdrant and Ollama as reachable
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            errors = initializer.validate_config()

        # Directory creation errors should not be present
        sqlite_errors = [e for e in errors if e.component == "sqlite"]
        assert len(sqlite_errors) == 0

        # Directories should be created
        assert (tmp_path / "new_dir").exists()
        assert (tmp_path / "new_dir2").exists()

    def test_validate_config_qdrant_unreachable(self, config: RepositoryConfig) -> None:
        """validate_config reports error when Qdrant is unreachable."""
        initializer = RepositoryInitializer(config)

        with patch("httpx.get", side_effect=Exception("Connection refused")):
            errors = initializer.validate_config()

        qdrant_errors = [e for e in errors if e.component == "qdrant"]
        assert len(qdrant_errors) == 1
        assert qdrant_errors[0].severity == "critical"
        assert "unreachable" in qdrant_errors[0].message.lower()

    def test_validate_config_cohere_missing_key(self, tmp_path: Path) -> None:
        """validate_config reports error when Cohere API key is missing."""
        config = RepositoryConfig(
            sqlite_path=tmp_path / "test.db",
            bm25_index_path=tmp_path / "bm25.pkl",
            embedding_provider_type="cohere",
            cohere_api_key=None,
        )
        initializer = RepositoryInitializer(config)

        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            errors = initializer.validate_config()

        embedding_errors = [e for e in errors if e.component == "embedding"]
        assert len(embedding_errors) == 1
        assert "api key" in embedding_errors[0].message.lower()

    def test_validate_config_unknown_provider(self, tmp_path: Path) -> None:
        """validate_config reports error for unknown provider type."""
        config = RepositoryConfig(
            sqlite_path=tmp_path / "test.db",
            bm25_index_path=tmp_path / "bm25.pkl",
            embedding_provider_type="unknown_provider",
        )
        initializer = RepositoryInitializer(config)

        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            errors = initializer.validate_config()

        embedding_errors = [e for e in errors if e.component == "embedding"]
        assert len(embedding_errors) == 1
        assert "unknown" in embedding_errors[0].message.lower()

    def test_validate_config_all_valid(self, config: RepositoryConfig) -> None:
        """validate_config returns empty list when all checks pass."""
        initializer = RepositoryInitializer(config)

        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            errors = initializer.validate_config()

        assert len(errors) == 0


# =============================================================================
# Initialization Tests
# =============================================================================


class TestInitialize:
    """Tests for initialize method."""

    def test_initialize_creates_all_components(self, initializer: RepositoryInitializer) -> None:
        """initialize() creates SQLite, Qdrant, BM25, and Embedding."""
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            state = initializer.initialize()

        assert state is not None
        assert state.is_healthy
        assert len(state.components) == 4

        component_names = {c.name for c in state.components}
        assert component_names == {"sqlite", "qdrant", "bm25", "embedding"}

    def test_initialize_returns_correct_state(self, initializer: RepositoryInitializer) -> None:
        """initialize() returns RepositoryState with correct counts."""
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            state = initializer.initialize()

        assert state.schema_version == "1.0.0"
        assert state.sqlite_count == 0
        assert state.qdrant_count == 0
        assert state.bm25_count == 0
        assert state.is_healthy

    def test_initialize_idempotent(self, initializer: RepositoryInitializer) -> None:
        """Calling initialize() twice does not fail."""
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            state1 = initializer.initialize()
            state2 = initializer.initialize()

        assert state1.is_healthy
        assert state2.is_healthy

    def test_initialize_fails_on_qdrant_error(self, initializer: RepositoryInitializer) -> None:
        """initialize() raises when Qdrant fails."""
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            with patch("app.services.repository.initializer.QdrantVectorStore") as mock_qdrant:
                mock_qdrant.side_effect = Exception("Qdrant down")

                with pytest.raises(RepositoryInitializationError, match="Qdrant"):
                    initializer.initialize()

    def test_initialize_fails_on_validation_error(self, tmp_path: Path) -> None:
        """initialize() raises when config validation fails."""
        config = RepositoryConfig(
            sqlite_path=tmp_path / "test.db",
            bm25_index_path=tmp_path / "bm25.pkl",
            embedding_provider_type="unknown",
        )
        initializer = RepositoryInitializer(config)

        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            with pytest.raises(RepositoryInitializationError, match="validation failed"):
                initializer.initialize()


# =============================================================================
# Component Access Tests
# =============================================================================


class TestComponentAccess:
    """Tests for accessing components before/after initialization."""

    def test_access_before_init_raises(self, initializer: RepositoryInitializer) -> None:
        """Accessing components before initialize() raises error."""
        with pytest.raises(RepositoryNotInitializedError):
            _ = initializer.sqlite_store

        with pytest.raises(RepositoryNotInitializedError):
            _ = initializer.qdrant_store

        with pytest.raises(RepositoryNotInitializedError):
            _ = initializer.bm25_index

        with pytest.raises(RepositoryNotInitializedError):
            _ = initializer.embedding_provider

    def test_access_after_init_succeeds(self, initializer: RepositoryInitializer) -> None:
        """Accessing components after initialize() succeeds."""
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            initializer.initialize()

        assert initializer.sqlite_store is not None
        assert initializer.qdrant_store is not None
        assert initializer.bm25_index is not None
        assert initializer.embedding_provider is not None


# =============================================================================
# Schema Version Tests
# =============================================================================


class TestSchemaVersion:
    """Tests for simple schema version check (GAP-007 deferred)."""

    def test_schema_version_table_created(self, initializer: RepositoryInitializer) -> None:
        """initialize() creates schema_version table."""
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            initializer.initialize()

        conn = initializer.sqlite_store.conn_manager.get_connection()
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()

        assert row is not None
        assert row[0] == "1.0.0"

    def test_schema_version_idempotent(self, initializer: RepositoryInitializer) -> None:
        """Running initialize() twice does not duplicate version entries."""
        with patch("httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            initializer.initialize()
            initializer.initialize()

        conn = initializer.sqlite_store.conn_manager.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]

        assert count == 1


# =============================================================================
# RepositoryState Tests
# =============================================================================


class TestRepositoryState:
    """Tests for RepositoryState dataclass."""

    def test_is_healthy_all_available(self) -> None:
        """is_healthy returns True when all components available."""
        state = RepositoryState(
            schema_version="1.0.0",
            sqlite_count=10,
            qdrant_count=10,
            bm25_count=10,
            initialized_at=__import__("datetime").datetime.now(),
            components=[
                ComponentStatus(name="sqlite", available=True),
                ComponentStatus(name="qdrant", available=True),
            ],
        )
        assert state.is_healthy is True

    def test_is_healthy_one_unavailable(self) -> None:
        """is_healthy returns False when any component unavailable."""
        state = RepositoryState(
            schema_version="1.0.0",
            sqlite_count=10,
            qdrant_count=0,
            bm25_count=10,
            initialized_at=__import__("datetime").datetime.now(),
            components=[
                ComponentStatus(name="sqlite", available=True),
                ComponentStatus(name="qdrant", available=False, message="down"),
            ],
        )
        assert state.is_healthy is False

    def test_is_healthy_empty_components(self) -> None:
        """is_healthy returns True when no components (vacuous truth)."""
        state = RepositoryState(
            schema_version="1.0.0",
            sqlite_count=0,
            qdrant_count=0,
            bm25_count=0,
            initialized_at=__import__("datetime").datetime.now(),
            components=[],
        )
        assert state.is_healthy is True
