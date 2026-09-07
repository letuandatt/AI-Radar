"""SQLite-based KnowledgeStore implementation.

Implements the KnowledgeStore protocol with SQLite persistence,
providing idempotent ingestion, retry logic, timeout handling,
and circuit breaker behavior.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logger import get_logger
from app.models.knowledge_object import KnowledgeObject
from app.models.metadata import ExtractionResult
from app.storage.knowledge.base import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    SQLiteConnectionManager,
    retry_on_transient_error,
)
from app.storage.knowledge.knowledge_store import SaveResult
from app.storage.knowledge.schema import ALL_DDL_STATEMENTS

logger = get_logger(__name__)


_SELECT_COLUMNS = """
    id,
    source_type,
    source_name,
    external_id,
    content_hash,
    source_url,
    title,
    content_text,
    metadata_json,
    fetched_at,
    published_at,
    created_at,
    updated_at,
    parser_version,
    normalizer_version,
    extractor_version
"""


class SQLiteKnowledgeStore:
    """SQLite-backed KnowledgeStore with idempotent save semantics.

    Thread Safety:
        All database operations are serialized by an internal lock.
        This avoids SQLite API misuse when the store is shared across threads.
    """

    def __init__(
        self,
        db_path: str | Path = "app/storage/knowledge/knowledge.db",
        timeout: float = 30.0,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._conn_manager = SQLiteConnectionManager(db_path, timeout=timeout)
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._op_lock = threading.RLock()
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._op_lock:
            conn = self._conn_manager.get_connection()
            try:
                for ddl in ALL_DDL_STATEMENTS:
                    conn.execute(ddl)
                conn.commit()
                logger.info(
                    "SQLite schema initialized: %s",
                    self._conn_manager.db_path,
                )
            except sqlite3.Error as e:
                conn.rollback()
                logger.error("Failed to initialize schema: %s", e)
                raise

    # ------------------------------------------------------------------
    # Circuit Breaker
    # ------------------------------------------------------------------

    def _check_circuit(self) -> None:
        """Raise if circuit breaker is open."""
        if not self._circuit_breaker.allow_request():
            raise CircuitBreakerOpenError(
                "SQLiteKnowledgeStore circuit breaker is open. "
                "Operations are temporarily suspended."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_objects(self, objects: list[KnowledgeObject]) -> SaveResult:
        """Persist KnowledgeObjects with idempotent semantics.

        Rules:
        - Identity not found -> CREATE
        - Identity found + content_hash differs -> UPDATE
        - Identity found + content_hash same -> SKIP
        """
        self._check_circuit()

        try:
            result = self._save_objects_with_retry(objects)
        except sqlite3.OperationalError:
            self._circuit_breaker.record_failure()
            raise

        self._circuit_breaker.record_success()
        return result  # type: ignore[no-any-return]

    def get_by_external_id(self, external_id: str, source_type: str) -> KnowledgeObject | None:
        """Retrieve a KnowledgeObject by external identity."""
        self._check_circuit()

        with self._op_lock:
            conn = self._conn_manager.get_connection()
            row = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM knowledge_objects
                WHERE external_id = ? AND source_type = ?
                LIMIT 1
                """,
                (external_id, source_type),
            ).fetchone()

            if row is None:
                return None
            return self._row_to_knowledge_object(row)

    def get_by_content_hash(self, content_hash: str) -> KnowledgeObject | None:
        """Retrieve a KnowledgeObject by content hash."""
        self._check_circuit()

        with self._op_lock:
            conn = self._conn_manager.get_connection()
            row = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM knowledge_objects
                WHERE content_hash = ?
                LIMIT 1
                """,
                (content_hash,),
            ).fetchone()

            if row is None:
                return None
            return self._row_to_knowledge_object(row)

    def get_all(self) -> list[KnowledgeObject]:
        """Retrieve all stored KnowledgeObjects."""
        self._check_circuit()

        with self._op_lock:
            conn = self._conn_manager.get_connection()
            rows = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM knowledge_objects
                """
            ).fetchall()

            return [self._row_to_knowledge_object(row) for row in rows]

    def count(self) -> int:
        """Return the total number of stored KnowledgeObjects."""
        self._check_circuit()

        with self._op_lock:
            conn = self._conn_manager.get_connection()
            row = conn.execute("SELECT COUNT(*) FROM knowledge_objects").fetchone()
            return int(row[0])

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._op_lock:
            self._conn_manager.close()

    # ------------------------------------------------------------------
    # Save internals
    # ------------------------------------------------------------------

    @retry_on_transient_error(
        max_retries=3,
        base_delay=0.5,
        retryable_exceptions=(sqlite3.OperationalError,),
    )
    def _save_objects_with_retry(self, objects: list[KnowledgeObject]) -> SaveResult:
        """Retry wrapper around the atomic save operation."""
        return self._save_objects_atomic(objects)

    def _save_objects_atomic(self, objects: list[KnowledgeObject]) -> SaveResult:
        """Run save_objects as one serialized transaction."""
        created = 0
        updated = 0
        skipped = 0

        with self._op_lock:
            conn = self._conn_manager.get_connection()

            with conn:
                for obj in objects:
                    existing = self._find_existing_identity(
                        conn=conn,
                        source_type=obj.source_type,
                        source_name=obj.source_name,
                        external_id=obj.external_id,
                    )

                    if existing is None:
                        self._insert_object(conn, obj)
                        created += 1
                        logger.debug(
                            "Created KnowledgeObject %s (external_id=%s)",
                            obj.id,
                            obj.external_id,
                        )
                        continue

                    existing_id, existing_hash = existing

                    if existing_hash != obj.content_hash:
                        self._update_object(conn, existing_id, obj)
                        updated += 1
                        logger.debug(
                            "Updated KnowledgeObject %s (external_id=%s)",
                            existing_id,
                            obj.external_id,
                        )
                    else:
                        skipped += 1
                        logger.debug(
                            "Skipped KnowledgeObject %s (content unchanged)",
                            obj.id,
                        )

        logger.info(
            "save_objects completed: %d created, %d updated, %d skipped",
            created,
            updated,
            skipped,
        )

        return SaveResult(created=created, updated=updated, skipped=skipped)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_existing_identity(
        self,
        conn: sqlite3.Connection,
        source_type: str,
        source_name: str,
        external_id: str,
    ) -> tuple[str, str] | None:
        """Find existing record by identity triple.

        Returns:
            Tuple of (id, content_hash), or None if not found.
        """
        row = conn.execute(
            """
            SELECT id, content_hash
            FROM knowledge_objects
            WHERE source_type = ? AND source_name = ? AND external_id = ?
            LIMIT 1
            """,
            (source_type, source_name, external_id),
        ).fetchone()

        if row is None:
            return None

        return str(row[0]), str(row[1])

    def _insert_object(self, conn: sqlite3.Connection, obj: KnowledgeObject) -> None:
        """Insert a new KnowledgeObject."""
        now = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            INSERT INTO knowledge_objects (
                id,
                source_type,
                source_name,
                external_id,
                content_hash,
                source_url,
                title,
                content_text,
                metadata_json,
                fetched_at,
                published_at,
                created_at,
                updated_at,
                parser_version,
                normalizer_version,
                extractor_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                obj.id,
                obj.source_type,
                obj.source_name,
                obj.external_id,
                obj.content_hash,
                obj.source_url,
                obj.title,
                obj.content_text,
                obj.metadata.model_dump_json(),
                self._to_iso(obj.fetched_at),
                self._to_iso(obj.published_at),
                now,
                now,
                obj.parser_version,
                obj.normalizer_version,
                obj.extractor_version,
            ),
        )

    def _update_object(
        self,
        conn: sqlite3.Connection,
        existing_id: str,
        obj: KnowledgeObject,
    ) -> None:
        """Update an existing KnowledgeObject by internal id."""
        now = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            UPDATE knowledge_objects
            SET
                content_hash = ?,
                source_url = ?,
                title = ?,
                content_text = ?,
                metadata_json = ?,
                published_at = ?,
                updated_at = ?,
                parser_version = ?,
                normalizer_version = ?,
                extractor_version = ?
            WHERE id = ?
            """,
            (
                obj.content_hash,
                obj.source_url,
                obj.title,
                obj.content_text,
                obj.metadata.model_dump_json(),
                self._to_iso(obj.published_at),
                now,
                obj.parser_version,
                obj.normalizer_version,
                obj.extractor_version,
                existing_id,
            ),
        )

    def _row_to_knowledge_object(self, row: tuple[Any, ...]) -> KnowledgeObject:
        """Convert a SELECT row into a KnowledgeObject."""
        return KnowledgeObject(
            id=row[0],
            source_type=row[1],
            source_name=row[2],
            external_id=row[3],
            content_hash=row[4],
            source_url=row[5],
            title=row[6],
            content_text=row[7],
            metadata=ExtractionResult.model_validate_json(row[8]),
            fetched_at=self._parse_dt(row[9]),  # type: ignore[arg-type]
            published_at=self._parse_dt(row[10]),
            created_at=self._parse_dt(row[11]),  # type: ignore[arg-type]
            updated_at=self._parse_dt(row[12]),  # type: ignore[arg-type]
            parser_version=row[13],
            normalizer_version=row[14],
            extractor_version=row[15],
            embedding_vector=None,
            vector_db_id=None,
        )

    @staticmethod
    def _to_iso(value: datetime | None) -> str | None:
        """Convert datetime to ISO string or None."""
        if value is None:
            return None
        return value.isoformat()

    @staticmethod
    def _parse_dt(value: Any) -> datetime | None:
        """Parse ISO datetime string from SQLite."""
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))
