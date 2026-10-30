"""Read-only SQLite browsing with bounded, parameterized queries."""

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class SQLiteBrowseStore:
    """Use an independent read-only connection per operation, safe for worker threads."""

    def __init__(self, path: str | Path) -> None:
        self._uri = Path(path).resolve().as_uri() + "?mode=ro"

    def page(
        self,
        *,
        source_types: list[str],
        source_names: list[str],
        topics: list[str],
        published_after: str | None,
        published_before: str | None,
        sort_field: str,
        sort_direction: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Count and fetch in one read transaction; SQL identifiers are allowlisted."""
        if sort_field not in {"published_at", "created_at", "source_type", "title"}:
            raise ValueError("Unsupported sort field")
        if sort_direction not in {"asc", "desc"} or not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Invalid pagination")
        clauses, values = ["deleted_at IS NULL"], []
        for column, choices in (("source_type", source_types), ("source_name", source_names)):
            if choices:
                clauses.append(f"{column} IN ({','.join('?' for _ in choices)})")
                values.extend(choices)
        if topics:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(metadata_json, '$.topics') "
                f"WHERE value IN ({','.join('?' for _ in topics)}))"
            )
            values.extend(topics)
        for operator, value in ((">=", published_after), ("<=", published_before)):
            if value is not None:
                clauses.append(f"julianday(published_at) {operator} julianday(?)")
                values.append(value)
        where = " AND ".join(clauses)
        expression = f"julianday({sort_field})" if sort_field.endswith("_at") else sort_field
        with closing(sqlite3.connect(self._uri, uri=True, timeout=5)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            total = connection.execute(
                f"SELECT count(*) FROM knowledge_objects WHERE {where}", values
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT id, title, source_type, source_name, published_at, created_at, "
                "content_hash, metadata_json FROM knowledge_objects "
                f"WHERE {where} ORDER BY {sort_field} IS NULL, {expression} {sort_direction}, "
                "id ASC LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
            return [dict(row) for row in rows], int(total)
