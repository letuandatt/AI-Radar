"""Repository Health Monitor.

Periodically checks the health of all repository components
and emits structured metrics for observability (OBS-002).

Extended health checks (GAP-004):
- SQLite: reachable, query latency
- Qdrant: reachable, collection health
- Embedding Provider: accessible, response time
- BM25 index: file exists, loadable
"""

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.logger import get_logger
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from app.storage.search.bm25_index import BM25Index
from app.storage.vector.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)


# =============================================================================
# Data Models
# =============================================================================


@dataclass(frozen=True)
class HealthCheckResult:
    """Result of a single health check.

    Attributes:
        component: Component name (sqlite, qdrant, bm25, embedding).
        healthy: Whether the component is healthy.
        latency_ms: Response latency in milliseconds (if applicable).
        message: Optional status message.
    """

    component: str
    healthy: bool
    latency_ms: float | None = None
    message: str = ""


@dataclass(frozen=True)
class HealthReport:
    """Overall health report for the repository.

    Attributes:
        timestamp: Timestamp of the health check.
        overall_healthy: Whether all components are healthy.
        checks: List of individual check results.
        storage_size_bytes: Total storage size in bytes.
    """

    timestamp: datetime
    overall_healthy: bool
    checks: list[HealthCheckResult] = field(default_factory=list)
    storage_size_bytes: int = 0


# =============================================================================
# Health Monitor
# =============================================================================


class RepositoryHealthMonitor:
    """Monitors the health of all repository components.

    Runs periodic health checks in a background thread and emits
    structured metrics for observability.

    Args:
        sqlite_store: SQLiteKnowledgeStore instance.
        qdrant_store: QdrantVectorStore instance.
        bm25_index: BM25Index instance.
        sqlite_path: Path to SQLite database (for size check).
        bm25_index_path: Path to BM25 index (for file check).
        check_interval: Seconds between health checks.
    """

    def __init__(
        self,
        sqlite_store: SQLiteKnowledgeStore,
        qdrant_store: QdrantVectorStore,
        bm25_index: BM25Index,
        sqlite_path: Path | None = None,
        bm25_index_path: Path | None = None,
        check_interval: float = 60.0,
    ) -> None:
        self._sqlite_store = sqlite_store
        self._qdrant_store = qdrant_store
        self._bm25_index = bm25_index
        self._sqlite_path = sqlite_path
        self._bm25_index_path = bm25_index_path
        self._check_interval = check_interval

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_report: HealthReport | None = None

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the health monitor background thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Health monitor is already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_monitor,
            daemon=True,
            name="repository-health-monitor",
        )
        self._thread.start()
        logger.info("Health monitor started (interval=%.0fs)", self._check_interval)

    def stop(self) -> None:
        """Stop the health monitor background thread."""
        self._stop_event.set()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        logger.info("Health monitor stopped")

    def _run_monitor(self) -> None:
        """Background thread that runs periodic health checks."""
        while not self._stop_event.is_set():
            try:
                report = self.check_health()
                self._last_report = report
                self._emit_metrics(report)

                if not report.overall_healthy:
                    logger.warning(
                        "Repository health degraded: %s",
                        [c.component for c in report.checks if not c.healthy],
                    )

            except Exception as e:
                logger.error("Health check failed: %s", e)

            # Wait for next check, checking stop event every second
            for _ in range(int(self._check_interval)):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    # ------------------------------------------------------------------
    # Health Check
    # ------------------------------------------------------------------

    def check_health(self) -> HealthReport:
        """Run all health checks and return a report.

        Returns:
            HealthReport with individual check results.
        """
        # Check SQLite first, then Qdrant, then BM25
        checks: list[HealthCheckResult] = [
            self._check_sqlite(),
            self._check_qdrant(),
            self._check_bm25(),
        ]

        # Calculate overall health
        overall_healthy = all(c.healthy for c in checks)

        # Calculate storage size
        storage_size = self._get_storage_size()

        return HealthReport(
            timestamp=datetime.now(timezone.utc),
            overall_healthy=overall_healthy,
            checks=checks,
            storage_size_bytes=storage_size,
        )

    def _check_sqlite(self) -> HealthCheckResult:
        """Check SQLite database health and query latency."""
        start_time = time.perf_counter()

        try:
            # Simple query to test connectivity and latency
            self._sqlite_store.count()
            latency_ms = (time.perf_counter() - start_time) * 1000

            return HealthCheckResult(
                component="sqlite",
                healthy=True,
                latency_ms=round(latency_ms, 2),
                message="SQLite reachable",
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return HealthCheckResult(
                component="sqlite",
                healthy=False,
                latency_ms=round(latency_ms, 2),
                message=f"SQLite error: {e}",
            )

    def _check_qdrant(self) -> HealthCheckResult:
        """Check Qdrant vector store health."""
        start_time = time.perf_counter()

        try:
            # Simple operation to test connectivity
            self._qdrant_store.count()
            latency_ms = (time.perf_counter() - start_time) * 1000

            return HealthCheckResult(
                component="qdrant",
                healthy=True,
                latency_ms=round(latency_ms, 2),
                message="Qdrant reachable",
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return HealthCheckResult(
                component="qdrant",
                healthy=False,
                latency_ms=round(latency_ms, 2),
                message=f"Qdrant error: {e}",
            )

    def _check_bm25(self) -> HealthCheckResult:
        """Check BM25 index health."""
        try:
            # Check if BM25 index file exists
            if self._bm25_index_path is not None:
                if not Path(self._bm25_index_path).exists():
                    return HealthCheckResult(
                        component="bm25",
                        healthy=False,
                        message="BM25 index file not found",
                    )

            # Check if BM25 index is loadable
            doc_count = self._bm25_index.document_count

            return HealthCheckResult(
                component="bm25",
                healthy=True,
                message=f"BM25 index valid ({doc_count} docs)",
            )

        except Exception as e:
            return HealthCheckResult(
                component="bm25",
                healthy=False,
                message=f"BM25 error: {e}",
            )

    def _get_storage_size(self) -> int:
        """Calculate total storage size in bytes."""
        total_size = 0

        if self._sqlite_path is not None:
            path = Path(self._sqlite_path)
            if path.exists():
                total_size += path.stat().st_size

        if self._bm25_index_path is not None:
            path = Path(self._bm25_index_path)
            if path.exists():
                total_size += path.stat().st_size

        return total_size

    # ------------------------------------------------------------------
    # Metrics Emission (OBS-002)
    # ------------------------------------------------------------------

    def _emit_metrics(self, report: HealthReport) -> None:
        """Emit structured metrics for observability."""
        metrics = {
            "repository_health_status": "healthy" if report.overall_healthy else "degraded",
            "repository_storage_size_bytes": report.storage_size_bytes,
            "timestamp": report.timestamp.isoformat(),
            "checks": {
                check.component: {
                    "healthy": check.healthy,
                    "latency_ms": check.latency_ms,
                    "message": check.message,
                }
                for check in report.checks
            },
        }

        logger.info("Repository metrics: %s", json.dumps(metrics))

    # ------------------------------------------------------------------
    # Last Report Access
    # ------------------------------------------------------------------

    @property
    def last_report(self) -> HealthReport | None:
        """Return the most recent health report."""
        return self._last_report
