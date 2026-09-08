"""SQLite-based KnowledgeStore implementation.

Implements the KnowledgeStore protocol with SQLite persistence,
providing idempotent ingestion, retry logic, timeout handling,
and circuit breaker behavior.
"""

import sqlite3
import threading
from dataclasses import dataclass
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


@dataclass(frozen=True)
class UpdateResult:
    """Result of a batch_update() operation.

    Attributes:
        updated: Number of objects successfully updated.
        skipped: Number of objects skipped (ID not found).
    """

    updated: int
    skipped: int

    @property
    def total_processed(self) -> int:
        """Total number of objects processed."""
        return self.updated + self.skipped


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

    def get_by_id(self, obj_id: str) -> KnowledgeObject | None:
        """Retrieve a KnowledgeObject by internal ID.

        Args:
            obj_id: The internal UUID of the object.

        Returns:
            The matching KnowledgeObject, or None if not found.
        """
        self._check_circuit()

        with self._op_lock:
            conn = self._conn_manager.get_connection()
            row = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM knowledge_objects
                WHERE id = ?
                LIMIT 1
                """,
                (obj_id,),
            ).fetchone()

            if row is None:
                return None
            return self._row_to_knowledge_object(row)

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

    # ------------------------------------------------------------------
    # Update Operations
    # ------------------------------------------------------------------

    def update_by_id(self, obj_id: str, updates: dict[str, Any]) -> bool:
        """Partial update: chỉ update fields được chỉ định.

        Allowed fields (whitelist):
            - title, content_text, source_url, published_at
            - metadata (ExtractionResult)
            - embedding_vector, vector_db_id

        Forbidden fields (identity + immutable):
            - id, source_type, source_name, external_id
            - created_at, fetched_at, content_hash
            - parser_version, normalizer_version, extractor_version

        Args:
            obj_id: Internal ID of the KnowledgeObject.
            updates: Dict of field names to new values.

        Returns:
            True if updated, False if not found.

        Raises:
            ValueError: If updates contain forbidden fields.
        """
        FORBIDDEN_FIELDS = {
            "id",
            "source_type",
            "source_name",
            "external_id",
            "created_at",
            "fetched_at",
            "parser_version",
            "normalizer_version",
            "extractor_version",
        }

        invalid = set(updates.keys()) & FORBIDDEN_FIELDS
        if invalid:
            raise ValueError(
                f"Cannot update forbidden fields: {invalid}. "
                f"Allowed fields: {set(updates.keys()) - FORBIDDEN_FIELDS}"
            )

        if not updates:
            return False

        self._check_circuit()

        with self._op_lock:
            conn = self._conn_manager.get_connection()

            # Check if exists
            existing = conn.execute(
                "SELECT id FROM knowledge_objects WHERE id = ? LIMIT 1",
                (obj_id,),
            ).fetchone()

            if existing is None:
                return False

            # Build UPDATE query dynamically
            set_clauses: list[str] = []
            values: list[Any] = []

            for field, value in updates.items():
                if field == "metadata" and value is not None:
                    # Serialize ExtractionResult to JSON
                    set_clauses.append("metadata_json = ?")
                    values.append(value.model_dump_json())
                elif field == "published_at":
                    set_clauses.append("published_at = ?")
                    values.append(self._to_iso(value))
                else:
                    set_clauses.append(f"{field} = ?")
                    values.append(value)

            # Always update updated_at
            now = datetime.now(timezone.utc).isoformat()
            set_clauses.append("updated_at = ?")
            values.append(now)

            values.append(obj_id)

            query = f"UPDATE knowledge_objects SET {', '.join(set_clauses)} WHERE id = ?"
            conn.execute(query, values)
            conn.commit()

            logger.debug(
                "Updated KnowledgeObject %s: fields=%s",
                obj_id,
                list(updates.keys()),
            )
            return True

    def update_metadata_by_id(self, obj_id: str, new_metadata: ExtractionResult) -> bool:
        """Update chỉ metadata JSON, giữ nguyên các field khác.

        Args:
            obj_id: Internal ID of the KnowledgeObject.
            new_metadata: New ExtractionResult to replace existing.

        Returns:
            True if updated, False if not found.
        """
        return self.update_by_id(obj_id, {"metadata": new_metadata})

    def update_content_by_id(self, obj_id: str, new_title: str, new_content: str) -> bool:
        """Update title + content_text + recalculate content_hash.

        Args:
            obj_id: Internal ID of the KnowledgeObject.
            new_title: New title.
            new_content: New content text.

        Returns:
            True if updated, False if not found.
        """
        from app.core.utils import compute_text_hash

        new_hash = compute_text_hash(new_content)
        return self.update_by_id(
            obj_id,
            {
                "title": new_title,
                "content_text": new_content,
                "content_hash": new_hash,
            },
        )

    def touch_by_id(self, obj_id: str) -> bool:
        """Chỉ update updated_at timestamp.

        Dùng cho heartbeat, cache invalidation, hoặc marking as recently accessed.

        Args:
            obj_id: Internal ID of the KnowledgeObject.

        Returns:
            True if touched, False if not found.
        """
        self._check_circuit()

        with self._op_lock:
            conn = self._conn_manager.get_connection()

            now = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                "UPDATE knowledge_objects SET updated_at = ? WHERE id = ?",
                (now, obj_id),
            )
            conn.commit()

            return cursor.rowcount > 0

    def batch_update(self, objects: list[KnowledgeObject]) -> "UpdateResult":
        """Explicit batch update (idempotent).

        Objects phải có ID hợp lệ (đã tồn tại trong DB).
        - Nếu ID không tồn tại → skip
        - Nếu ID tồn tại → update toàn bộ mutable fields

        Args:
            objects: List of KnowledgeObjects to update.

        Returns:
            UpdateResult with updated and skipped counts.
        """
        self._check_circuit()

        updated = 0
        skipped = 0

        with self._op_lock:
            conn = self._conn_manager.get_connection()

            with conn:
                for obj in objects:
                    existing = conn.execute(
                        "SELECT id FROM knowledge_objects WHERE id = ? LIMIT 1",
                        (obj.id,),
                    ).fetchone()

                    if existing is None:
                        skipped += 1
                        logger.debug("Skipped update for non-existent ID: %s", obj.id)
                        continue

                    self._update_object(conn, obj.id, obj)
                    updated += 1

        logger.info(
            "batch_update completed: %d updated, %d skipped",
            updated,
            skipped,
        )

        return UpdateResult(updated=updated, skipped=skipped)

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
