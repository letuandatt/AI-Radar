"""Index Maintenance Service.

Orchestrates index rebuild, health checks, and SQLite optimization
across all storage layers (SQLite, Qdrant, BM25).

All operations emit structured JSON logs (GAP-011).
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.logger import get_logger
from app.models.knowledge_object import KnowledgeObject
from app.storage.knowledge.sqlite_store import SQLiteKnowledgeStore
from app.storage.search.bm25_index import BM25Document, BM25Index
from app.storage.vector.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)


@dataclass
class IndexHealthReport:
    """Report from check_index_health().

    Attributes:
        sqlite_count: Number of KnowledgeObjects in SQLite.
        qdrant_count: Number of vector points in Qdrant.
        bm25_count: Number of documents in BM25 index.
        orphaned_vector_ids: Point IDs in Qdrant but not in SQLite.
        missing_vector_ids: Object IDs in SQLite but not in Qdrant.
        is_consistent: True if all three stores are aligned.
    """

    sqlite_count: int
    qdrant_count: int
    bm25_count: int
    orphaned_vector_ids: list[str] = field(default_factory=list)
    missing_vector_ids: list[str] = field(default_factory=list)
    is_consistent: bool = False


class IndexMaintenanceService:
    """Orchestrates index maintenance across SQLite, Qdrant, and BM25.

    Args:
        sqlite_store: SQLiteKnowledgeStore instance.
        qdrant_store: Optional QdrantVectorStore instance.
        bm25_index: Optional BM25Index instance.
    """

    def __init__(
        self,
        sqlite_store: SQLiteKnowledgeStore,
        qdrant_store: QdrantVectorStore | None = None,
        bm25_index: BM25Index | None = None,
    ) -> None:
        self._sqlite_store = sqlite_store
        self._qdrant_store = qdrant_store
        self._bm25_index = bm25_index

    # ------------------------------------------------------------------
    # Structured Logging (GAP-011)
    # ------------------------------------------------------------------

    @staticmethod
    def _log_operation(
        operation: str,
        duration_ms: float,
        items_processed: int,
        status: str,
        error: str | None = None,
    ) -> None:
        """Emit a structured JSON log entry for an index operation.

        Args:
            operation: Operation name (e.g., "rebuild_all_indexes").
            duration_ms: Operation duration in milliseconds.
            items_processed: Number of items processed.
            status: "success" or "error".
            error: Error message if status is "error".
        """
        log_entry: dict[str, Any] = {
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
            "items_processed": items_processed,
            "status": status,
        }
        if error is not None:
            log_entry["error"] = error

        logger.info(json.dumps(log_entry))

    # ------------------------------------------------------------------
    # Rebuild All Indexes
    # ------------------------------------------------------------------

    def rebuild_all_indexes(self) -> dict[str, Any]:
        """Rebuild all indexes: SQLite, Qdrant optimizer, and BM25.

        Returns:
            Dict with rebuild results per component.

        Raises:
            Exception: If any rebuild step fails.
        """
        start_time = time.perf_counter()
        results: dict[str, Any] = {}
        total_items = 0

        try:
            # 1. Rebuild SQLite metadata indexes
            sqlite_created = self._sqlite_store.ensure_metadata_indexes()
            self._sqlite_store.optimize_metadata_indexes()
            results["sqlite_indexes_created"] = sqlite_created

            # 2. Trigger Qdrant optimizer
            if self._qdrant_store is not None:
                qdrant_result = self._qdrant_store.optimize_index()
                results["qdrant_optimizer"] = qdrant_result

            # 3. Rebuild BM25 index from SQLite data
            if self._bm25_index is not None:
                all_objects = self._sqlite_store.get_all()
                total_items = len(all_objects)
                bm25_docs = [self._to_bm25_document(obj) for obj in all_objects]
                bm25_count = self._bm25_index.build(bm25_docs)
                self._bm25_index.save()
                results["bm25_documents"] = bm25_count

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._log_operation(
                operation="rebuild_all_indexes",
                duration_ms=duration_ms,
                items_processed=total_items,
                status="success",
            )

            return results

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._log_operation(
                operation="rebuild_all_indexes",
                duration_ms=duration_ms,
                items_processed=total_items,
                status="error",
                error=str(e),
            )
            raise

    # ------------------------------------------------------------------
    # Index Health Check
    # ------------------------------------------------------------------

    def check_index_health(self) -> IndexHealthReport:
        """Check consistency between SQLite, Qdrant, and BM25.

        Detects orphaned vectors (in Qdrant but not SQLite) and
        missing vectors (in SQLite but not Qdrant).

        Returns:
            IndexHealthReport with counts and inconsistencies.
        """
        start_time = time.perf_counter()

        # Get SQLite IDs
        sqlite_objects = self._sqlite_store.get_all()
        sqlite_ids = {obj.id for obj in sqlite_objects}
        sqlite_count = len(sqlite_ids)

        # Get Qdrant IDs
        qdrant_count = 0
        qdrant_ids: set[str] = set()
        if self._qdrant_store is not None:
            qdrant_id_list = self._qdrant_store.get_all_point_ids()
            qdrant_ids = set(qdrant_id_list)
            qdrant_count = len(qdrant_ids)

        # Get BM25 IDs
        bm25_count = 0
        if self._bm25_index is not None:
            bm25_count = self._bm25_index.document_count

        # Find inconsistencies
        orphaned_vector_ids = sorted(qdrant_ids - sqlite_ids)
        missing_vector_ids = sorted(sqlite_ids - qdrant_ids)

        is_consistent = len(orphaned_vector_ids) == 0 and len(missing_vector_ids) == 0

        duration_ms = (time.perf_counter() - start_time) * 1000
        self._log_operation(
            operation="check_index_health",
            duration_ms=duration_ms,
            items_processed=sqlite_count,
            status="success",
        )

        return IndexHealthReport(
            sqlite_count=sqlite_count,
            qdrant_count=qdrant_count,
            bm25_count=bm25_count,
            orphaned_vector_ids=orphaned_vector_ids,
            missing_vector_ids=missing_vector_ids,
            is_consistent=is_consistent,
        )

    # ------------------------------------------------------------------
    # SQLite Optimization
    # ------------------------------------------------------------------

    def vacuum_sqlite(self) -> None:
        """Run VACUUM on the SQLite database to reclaim disk space.

        This rewrites the entire database file, removing fragmentation.
        """
        start_time = time.perf_counter()

        try:
            conn = self._sqlite_store.conn_manager.get_connection()
            conn.execute("VACUUM")
            conn.commit()

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._log_operation(
                operation="vacuum_sqlite",
                duration_ms=duration_ms,
                items_processed=0,
                status="success",
            )
            logger.info("SQLite VACUUM completed")

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._log_operation(
                operation="vacuum_sqlite",
                duration_ms=duration_ms,
                items_processed=0,
                status="error",
                error=str(e),
            )
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_bm25_document(obj: KnowledgeObject) -> BM25Document:
        """Convert a KnowledgeObject to a BM25Document.

        Args:
            obj: The KnowledgeObject to convert.

        Returns:
            BM25Document with combined title + content text.
        """
        text = f"{obj.title} {obj.content_text}"
        return BM25Document(
            id=obj.id,
            text=text,
            content_hash=obj.content_hash,
            published_at=obj.published_at,
        )
