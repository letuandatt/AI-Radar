"""Unit tests for IndexMaintenanceService."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core.utils import compute_text_hash
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.services.indexing.maintenance_service import (
    IndexHealthReport,
    IndexMaintenanceService,
)
from app.storage.search.bm25_index import BM25Index

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_sqlite_store():
    """Create a mock SQLiteKnowledgeStore."""
    store = MagicMock()
    store.ensure_metadata_indexes.return_value = 0
    store.get_all.return_value = []
    return store


@pytest.fixture
def mock_qdrant_store():
    """Create a mock QdrantVectorStore."""
    store = MagicMock()
    store.optimize_index.return_value = {"status": "green"}
    store.get_all_point_ids.return_value = []
    return store


@pytest.fixture
def bm25_index(tmp_path):
    """Create a real BM25Index with temp path."""
    return BM25Index(index_path=tmp_path / "test_bm25.pkl")


@pytest.fixture
def service(mock_sqlite_store, mock_qdrant_store, bm25_index):
    """Create IndexMaintenanceService with mocks."""
    return IndexMaintenanceService(
        sqlite_store=mock_sqlite_store,
        qdrant_store=mock_qdrant_store,
        bm25_index=bm25_index,
    )


def _make_ko(
    obj_id: str = "ko_001",
    content: str = "Test content",
) -> KnowledgeObject:
    """Helper to create a KnowledgeObject."""
    metadata = ExtractionResult(
        summary="Summary",
        topics=["AI"],
        entities=["Entity"],
        relevance_score=0.9,
    )
    ko = KnowledgeObject(
        source_type="rss",
        source_name="test_source",
        external_id=f"ext_{obj_id}",
        source_url=f"https://example.com/{obj_id}",
        content_hash=compute_text_hash(content),
        fetched_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        title="Test Title",
        content_text=content,
        metadata=metadata,
    )
    ko.id = obj_id
    return ko


# =============================================================================
# Rebuild All Indexes Tests
# =============================================================================


class TestRebuildAllIndexes:
    """Tests for rebuild_all_indexes method."""

    def test_rebuild_calls_all_components(
        self, service, mock_sqlite_store, mock_qdrant_store, bm25_index
    ) -> None:
        """rebuild_all_indexes calls SQLite, Qdrant, and BM25."""
        mock_sqlite_store.get_all.return_value = [
            _make_ko("ko_1", "Content one"),
            _make_ko("ko_2", "Content two"),
        ]

        results = service.rebuild_all_indexes()

        mock_sqlite_store.ensure_metadata_indexes.assert_called_once()
        mock_sqlite_store.optimize_metadata_indexes.assert_called_once()
        mock_qdrant_store.optimize_index.assert_called_once()
        assert results["bm25_documents"] == 2

    def test_rebuild_idempotent(self, service, mock_sqlite_store) -> None:
        """Running rebuild twice does not fail."""
        mock_sqlite_store.get_all.return_value = []

        service.rebuild_all_indexes()
        service.rebuild_all_indexes()

        assert mock_sqlite_store.ensure_metadata_indexes.call_count == 2

    def test_rebuild_without_qdrant(self, mock_sqlite_store, bm25_index) -> None:
        """rebuild works when Qdrant is not available."""
        service = IndexMaintenanceService(
            sqlite_store=mock_sqlite_store,
            qdrant_store=None,
            bm25_index=bm25_index,
        )
        mock_sqlite_store.get_all.return_value = []

        results = service.rebuild_all_indexes()
        assert "qdrant_optimizer" not in results

    def test_rebuild_without_bm25(self, mock_sqlite_store, mock_qdrant_store) -> None:
        """rebuild works when BM25 is not available."""
        service = IndexMaintenanceService(
            sqlite_store=mock_sqlite_store,
            qdrant_store=mock_qdrant_store,
            bm25_index=None,
        )

        results = service.rebuild_all_indexes()
        assert "bm25_documents" not in results


# =============================================================================
# Index Health Check Tests
# =============================================================================


class TestCheckIndexHealth:
    """Tests for check_index_health method."""

    def test_detects_orphaned_vectors(
        self, mock_sqlite_store, mock_qdrant_store, bm25_index
    ) -> None:
        """Detects vectors in Qdrant that have no matching KnowledgeObject."""
        # SQLite has 100 objects
        sqlite_objects = [_make_ko(f"ko_{i}") for i in range(100)]
        mock_sqlite_store.get_all.return_value = sqlite_objects

        # Qdrant has 98 points (2 orphaned)
        qdrant_ids = [f"ko_{i}" for i in range(98)] + ["orphan_1", "orphan_2"]
        mock_qdrant_store.get_all_point_ids.return_value = qdrant_ids

        service = IndexMaintenanceService(
            sqlite_store=mock_sqlite_store,
            qdrant_store=mock_qdrant_store,
            bm25_index=bm25_index,
        )

        report = service.check_index_health()

        assert report.sqlite_count == 100
        assert report.qdrant_count == 100
        assert len(report.orphaned_vector_ids) == 2
        assert "orphan_1" in report.orphaned_vector_ids
        assert "orphan_2" in report.orphaned_vector_ids
        assert report.is_consistent is False

    def test_detects_missing_vectors(
        self, mock_sqlite_store, mock_qdrant_store, bm25_index
    ) -> None:
        """Detects KnowledgeObjects in SQLite that have no Qdrant vector."""
        sqlite_objects = [_make_ko(f"ko_{i}") for i in range(10)]
        mock_sqlite_store.get_all.return_value = sqlite_objects

        # Qdrant only has 8 of the 10
        qdrant_ids = [f"ko_{i}" for i in range(8)]
        mock_qdrant_store.get_all_point_ids.return_value = qdrant_ids

        service = IndexMaintenanceService(
            sqlite_store=mock_sqlite_store,
            qdrant_store=mock_qdrant_store,
            bm25_index=bm25_index,
        )

        report = service.check_index_health()

        assert len(report.missing_vector_ids) == 2
        assert report.is_consistent is False

    def test_all_consistent(self, mock_sqlite_store, mock_qdrant_store, bm25_index) -> None:
        """Reports consistent when all stores are aligned."""
        sqlite_objects = [_make_ko(f"ko_{i}") for i in range(5)]
        mock_sqlite_store.get_all.return_value = sqlite_objects

        qdrant_ids = [f"ko_{i}" for i in range(5)]
        mock_qdrant_store.get_all_point_ids.return_value = qdrant_ids

        service = IndexMaintenanceService(
            sqlite_store=mock_sqlite_store,
            qdrant_store=mock_qdrant_store,
            bm25_index=bm25_index,
        )

        report = service.check_index_health()

        assert report.is_consistent is True
        assert len(report.orphaned_vector_ids) == 0
        assert len(report.missing_vector_ids) == 0

    def test_health_report_structure(
        self, mock_sqlite_store, mock_qdrant_store, bm25_index
    ) -> None:
        """IndexHealthReport has all required fields."""
        mock_sqlite_store.get_all.return_value = []
        mock_qdrant_store.get_all_point_ids.return_value = []

        service = IndexMaintenanceService(
            sqlite_store=mock_sqlite_store,
            qdrant_store=mock_qdrant_store,
            bm25_index=bm25_index,
        )

        report = service.check_index_health()

        assert isinstance(report, IndexHealthReport)
        assert isinstance(report.sqlite_count, int)
        assert isinstance(report.qdrant_count, int)
        assert isinstance(report.bm25_count, int)
        assert isinstance(report.orphaned_vector_ids, list)
        assert isinstance(report.missing_vector_ids, list)
        assert isinstance(report.is_consistent, bool)


# =============================================================================
# Vacuum Tests
# =============================================================================


class TestVacuumSqlite:
    """Tests for vacuum_sqlite method."""

    def test_vacuum_executes(self, mock_sqlite_store) -> None:
        """vacuum_sqlite executes VACUUM command."""
        mock_conn = MagicMock()
        mock_conn_manager = MagicMock()
        mock_conn_manager.get_connection.return_value = mock_conn

        # ✅ Set qua public property, không phải private attribute
        mock_sqlite_store.conn_manager = mock_conn_manager

        service = IndexMaintenanceService(sqlite_store=mock_sqlite_store)
        service.vacuum_sqlite()

        mock_conn.execute.assert_called_once_with("VACUUM")
        mock_conn.commit.assert_called_once()


# =============================================================================
# Structured Logging Tests (GAP-011)
# =============================================================================


class TestStructuredLogging:
    """Tests for structured JSON logging."""

    def test_rebuild_logs_json(self, service, mock_sqlite_store, caplog) -> None:
        """rebuild_all_indexes emits valid JSON log."""
        mock_sqlite_store.get_all.return_value = []

        import logging

        with caplog.at_level(logging.INFO):
            service.rebuild_all_indexes()

        # Find the JSON log entry
        json_logs = [record.message for record in caplog.records if record.message.startswith("{")]
        assert len(json_logs) >= 1

        log_data = json.loads(json_logs[-1])
        assert "operation" in log_data
        assert "duration_ms" in log_data
        assert "items_processed" in log_data
        assert "status" in log_data
        assert log_data["operation"] == "rebuild_all_indexes"
        assert log_data["status"] == "success"

    def test_health_check_logs_json(
        self, mock_sqlite_store, mock_qdrant_store, bm25_index, caplog
    ) -> None:
        """check_index_health emits valid JSON log."""
        mock_sqlite_store.get_all.return_value = []
        mock_qdrant_store.get_all_point_ids.return_value = []

        service = IndexMaintenanceService(
            sqlite_store=mock_sqlite_store,
            qdrant_store=mock_qdrant_store,
            bm25_index=bm25_index,
        )

        import logging

        with caplog.at_level(logging.INFO):
            service.check_index_health()

        json_logs = [record.message for record in caplog.records if record.message.startswith("{")]
        assert len(json_logs) >= 1

        log_data = json.loads(json_logs[-1])
        assert log_data["operation"] == "check_index_health"
        assert log_data["status"] == "success"

    def test_error_log_includes_error_field(self, mock_sqlite_store, caplog) -> None:
        """Error logs include the error field."""
        mock_sqlite_store.ensure_metadata_indexes.side_effect = Exception("disk full")

        service = IndexMaintenanceService(sqlite_store=mock_sqlite_store)

        import logging

        with caplog.at_level(logging.INFO):
            with pytest.raises(Exception, match="disk full"):
                service.rebuild_all_indexes()

        json_logs = [record.message for record in caplog.records if record.message.startswith("{")]
        assert len(json_logs) >= 1

        log_data = json.loads(json_logs[-1])
        assert log_data["status"] == "error"
        assert "error" in log_data
        assert "disk full" in log_data["error"]
