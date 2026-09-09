"""Metadata index management for SQLite knowledge storage.

This module centralizes metadata index definitions for the knowledge_objects
table. It allows new indexes to be added safely at runtime using idempotent
CREATE INDEX IF NOT EXISTS semantics.
"""

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class IndexDefinition:
    """Definition of a SQLite index.

    Attributes:
        name: Index name.
        table: Table name.
        columns: Column expressions, e.g. ("source_type", "published_at DESC").
        unique: Whether the index is UNIQUE.
        description: Human-readable purpose.
    """

    name: str
    table: str
    columns: tuple[str, ...]
    unique: bool = False
    description: str = ""

    def to_ddl(self) -> str:
        """Build CREATE INDEX statement."""
        unique_clause = "UNIQUE " if self.unique else ""
        column_clause = ", ".join(self.columns)

        return (
            f"CREATE {unique_clause}INDEX IF NOT EXISTS {self.name} "
            f"ON {self.table} ({column_clause})"
        )


def default_knowledge_indexes(
    table_name: str = "knowledge_objects",
) -> tuple[IndexDefinition, ...]:
    """Return default metadata indexes for the knowledge_objects table."""
    return (
        IndexDefinition(
            name="idx_knowledge_identity",
            table=table_name,
            columns=("source_type", "source_name", "external_id"),
            description="Identity lookup for idempotent upsert",
        ),
        IndexDefinition(
            name="idx_knowledge_content_hash",
            table=table_name,
            columns=("content_hash",),
            description="Content hash lookup for deduplication",
        ),
        IndexDefinition(
            name="idx_source_identity",
            table=table_name,
            columns=("source_type", "source_name"),
            description="Filter by source type and source name",
        ),
        IndexDefinition(
            name="idx_published_at",
            table=table_name,
            columns=("published_at",),
            description="Time-range filtering by published date",
        ),
        IndexDefinition(
            name="idx_created_at",
            table=table_name,
            columns=("created_at",),
            description="Time-range filtering by creation date",
        ),
        IndexDefinition(
            name="idx_updated_at",
            table=table_name,
            columns=("updated_at",),
            description="Time-range filtering by update date",
        ),
        IndexDefinition(
            name="idx_recent_by_source",
            table=table_name,
            columns=("source_type", "source_name", "published_at DESC"),
            description="Recent items per source",
        ),
        IndexDefinition(
            name="idx_knowledge_deleted_at",
            table=table_name,
            columns=("deleted_at",),
            description="Soft-delete filtering",
        ),
    )


class MetadataIndexManager:
    """Manages SQLite metadata indexes for KnowledgeObjects.

    Args:
        table_name: Target table name.
        indexes: Optional custom index definitions.
    """

    def __init__(
        self,
        table_name: str = "knowledge_objects",
        indexes: Sequence[IndexDefinition] | None = None,
    ) -> None:
        self._table_name = table_name
        self._indexes: tuple[IndexDefinition, ...] = (
            tuple(indexes) if indexes is not None else default_knowledge_indexes(table_name)
        )

    @property
    def table_name(self) -> str:
        """Return target table name."""
        return self._table_name

    @property
    def indexes(self) -> tuple[IndexDefinition, ...]:
        """Return managed index definitions."""
        return self._indexes

    def ensure_indexes(self, conn: sqlite3.Connection) -> int:
        """Create missing indexes.

        Args:
            conn: Active SQLite connection.

        Returns:
            Number of indexes created.
        """
        created = 0

        for index in self._indexes:
            if not self.index_exists(conn, index.name):
                conn.execute(index.to_ddl())
                created += 1
                logger.info(
                    "Created SQLite index '%s' on %s(%s)",
                    index.name,
                    index.table,
                    ", ".join(index.columns),
                )

        if created > 0:
            conn.commit()

        return created

    def index_exists(self, conn: sqlite3.Connection, index_name: str) -> bool:
        """Check whether an index exists.

        Args:
            conn: Active SQLite connection.
            index_name: Index name.

        Returns:
            True if index exists.
        """
        row = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'index' AND name = ?
            LIMIT 1
            """,
            (index_name,),
        ).fetchone()

        return row is not None

    def list_existing_indexes(self, conn: sqlite3.Connection) -> list[str]:
        """List existing non-system indexes on the target table.

        Args:
            conn: Active SQLite connection.

        Returns:
            Sorted list of index names.
        """
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name = ?
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """,
            (self._table_name,),
        ).fetchall()

        return [row[0] for row in rows]

    def analyze(self, conn: sqlite3.Connection) -> None:
        """Run ANALYZE to refresh SQLite query planner statistics."""
        conn.execute("ANALYZE")
        conn.commit()
        logger.info("ANALYZE completed for SQLite query planner")
