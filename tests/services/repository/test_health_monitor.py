"""Unit tests for RepositoryHealthMonitor (T161)."""

import json
from unittest.mock import MagicMock

import pytest

from app.services.repository.health_monitor import (
    HealthCheckResult,
    HealthReport,
    RepositoryHealthMonitor,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_sqlite_store():
    """Create a mock SQLiteKnowledgeStore."""
    store = MagicMock()
    store.count.return_value = 10
    return store


@pytest.fixture
def mock_qdrant_store():
    """Create a mock QdrantVectorStore."""
    store = MagicMock()
    store.count.return_value = 10
    return store


@pytest.fixture
def mock_bm25_index():
    """Create a mock BM25Index."""
    index = MagicMock()
    index.document_count = 10
    return index


@pytest.fixture
def monitor(mock_sqlite_store, mock_qdrant_store, mock_bm25_index, tmp_path):
    """Create a RepositoryHealthMonitor with mocks."""
    # Create BM25 index file so health check passes
    bm25_path = tmp_path / "bm25_index.pkl"
    bm25_path.touch()

    return RepositoryHealthMonitor(
        sqlite_store=mock_sqlite_store,
        qdrant_store=mock_qdrant_store,
        bm25_index=mock_bm25_index,
        sqlite_path=tmp_path / "knowledge.db",
        bm25_index_path=bm25_path,
        check_interval=1.0,
    )


# =============================================================================
# Health Check Tests
# =============================================================================


class TestCheckHealth:
    """Tests for check_health method."""

    def test_check_health_all_healthy(self, monitor) -> None:
        """check_health returns healthy when all components are up."""
        report = monitor.check_health()

        assert report.overall_healthy is True
        assert len(report.checks) == 3  # sqlite, qdrant, bm25

        for check in report.checks:
            assert check.healthy is True

    def test_check_health_qdrant_down(self, mock_sqlite_store, mock_bm25_index, tmp_path) -> None:
        """check_health detects Qdrant failure."""
        mock_qdrant_store = MagicMock()
        mock_qdrant_store.count.side_effect = Exception("Connection refused")

        monitor = RepositoryHealthMonitor(
            sqlite_store=mock_sqlite_store,
            qdrant_store=mock_qdrant_store,
            bm25_index=mock_bm25_index,
            sqlite_path=tmp_path / "knowledge.db",
            bm25_index_path=tmp_path / "bm25_index.pkl",
        )

        report = monitor.check_health()

        assert report.overall_healthy is False

        qdrant_check = next(c for c in report.checks if c.component == "qdrant")
        assert qdrant_check.healthy is False
        assert "Connection refused" in qdrant_check.message

    def test_check_health_sqlite_latency(self, monitor) -> None:
        """check_health measures SQLite query latency."""
        report = monitor.check_health()

        sqlite_check = next(c for c in report.checks if c.component == "sqlite")
        assert sqlite_check.latency_ms is not None
        assert sqlite_check.latency_ms >= 0

    def test_check_health_bm25_missing(
        self, mock_sqlite_store, mock_qdrant_store, tmp_path
    ) -> None:
        """check_health detects missing BM25 index file."""
        mock_bm25_index = MagicMock()
        mock_bm25_index.document_count = 0

        bm25_path = tmp_path / "nonexistent_bm25.pkl"

        monitor = RepositoryHealthMonitor(
            sqlite_store=mock_sqlite_store,
            qdrant_store=mock_qdrant_store,
            bm25_index=mock_bm25_index,
            bm25_index_path=bm25_path,
        )

        report = monitor.check_health()

        bm25_check = next(c for c in report.checks if c.component == "bm25")
        assert bm25_check.healthy is False
        assert "not found" in bm25_check.message

    def test_check_health_reports_storage_size(self, monitor, tmp_path) -> None:
        """check_health includes storage size in report."""
        # Create files with known sizes
        sqlite_path = tmp_path / "knowledge.db"
        sqlite_path.write_bytes(b"x" * 1000)

        report = monitor.check_health()

        assert report.storage_size_bytes >= 1000


# =============================================================================
# Monitor Start/Stop Tests
# =============================================================================


class TestMonitorStartStop:
    """Tests for monitor start and stop."""

    def test_monitor_start(self, monitor) -> None:
        """start() creates background thread."""
        monitor.start()
        assert monitor._thread is not None
        assert monitor._thread.is_alive()

        monitor.stop()

    def test_monitor_stop(self, monitor) -> None:
        """stop() terminates background thread."""
        monitor.start()
        monitor.stop()

        assert not monitor._thread.is_alive()

    def test_monitor_start_idempotent(self, monitor) -> None:
        """Calling start() twice does not create duplicate threads."""
        monitor.start()
        monitor.start()

        monitor.stop()

    def test_monitor_stop_idempotent(self, monitor) -> None:
        """Calling stop() when not running does not fail."""
        monitor.stop()


# =============================================================================
# Metrics Emission Tests
# =============================================================================


class TestMetricsEmission:
    """Tests for structured metrics emission."""

    def test_metrics_emitted_in_json(self, monitor, caplog) -> None:
        """Health check emits JSON metrics."""
        import logging

        with caplog.at_level(logging.INFO):
            report = monitor.check_health()
            monitor._emit_metrics(report)

        # Find JSON log entries
        json_logs = [
            record.message for record in caplog.records if "Repository metrics" in record.message
        ]

        assert len(json_logs) >= 1

        # Extract JSON from log message
        log_msg = json_logs[0]
        json_str = log_msg.split(": ", 1)[1]
        metrics = json.loads(json_str)

        assert "repository_health_status" in metrics
        assert "repository_storage_size_bytes" in metrics
        assert "timestamp" in metrics
        assert "checks" in metrics

    def test_last_report_property(self, monitor) -> None:
        """last_report property returns the most recent report."""
        assert monitor.last_report is None

        monitor.check_health()

        # After check_health, last_report is still None (it's set in _run_monitor)
        # But we can manually set it for testing
        report = monitor.check_health()
        monitor._last_report = report

        assert monitor.last_report is not None
        assert monitor.last_report.overall_healthy is True


# =============================================================================
# HealthCheckResult Tests
# =============================================================================


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_healthy_result(self) -> None:
        """HealthCheckResult for healthy component."""
        result = HealthCheckResult(
            component="sqlite",
            healthy=True,
            latency_ms=5.2,
            message="SQLite reachable",
        )

        assert result.component == "sqlite"
        assert result.healthy is True
        assert result.latency_ms == 5.2

    def test_unhealthy_result(self) -> None:
        """HealthCheckResult for unhealthy component."""
        result = HealthCheckResult(
            component="qdrant",
            healthy=False,
            latency_ms=None,
            message="Connection refused",
        )

        assert result.healthy is False
        assert result.latency_ms is None


# =============================================================================
# HealthReport Tests
# =============================================================================


class TestHealthReport:
    """Tests for HealthReport dataclass."""

    def test_healthy_report(self) -> None:
        """HealthReport with all healthy components."""
        checks = [
            HealthCheckResult(component="sqlite", healthy=True),
            HealthCheckResult(component="qdrant", healthy=True),
            HealthCheckResult(component="bm25", healthy=True),
        ]

        from datetime import datetime, timezone

        report = HealthReport(
            timestamp=datetime.now(timezone.utc),
            overall_healthy=True,
            checks=checks,
            storage_size_bytes=1000,
        )

        assert report.overall_healthy is True
        assert len(report.checks) == 3
        assert report.storage_size_bytes == 1000
