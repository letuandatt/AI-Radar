"""SQL operations for daily snapshots; callers own locks and transactions.

Only primitive records cross this boundary. No service models are imported.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def encode(value: Any) -> str:
    """Stable JSON encoding for persistence and optimistic input comparison."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def check_document_sources(conn: sqlite3.Connection, document: dict[str, Any]) -> None:
    """Verify all cited identities against live SQLite records in the transaction."""
    seen: dict[str, dict[str, Any]] = {}
    for section in document["sections"]:
        references = section["citations"] + [
            c for insight in section["insights"] for c in insight["citations"]
        ]
        for citation in references:
            identity = citation["knowledge_id"]
            if identity in seen and seen[identity] != citation:
                raise ValueError("Conflicting document citations")
            seen[identity] = citation
    for identity, citation in seen.items():
        row = conn.execute(
            "SELECT title, source_url, metadata_json FROM knowledge_objects "
            "WHERE id=? AND deleted_at IS NULL",
            (identity,),
        ).fetchone()
        if row is None or (row[0], row[1], json.loads(row[2])["relevance_score"]) != (
            citation["title"],
            citation["source_url"],
            citation["relevance_score"],
        ):
            raise ValueError(f"Intelligence citation changed or disappeared: {identity}")


def load_inputs(conn: sqlite3.Connection, date: str, start: str, end: str) -> dict[str, Any]:
    """Read current document and exact UTC publication cohort with fetched fallback."""
    stored = conn.execute(
        "SELECT payload_json FROM intelligence_documents WHERE report_date=?",
        (date,),
    ).fetchone()
    document = json.loads(stored[0]) if stored else None
    if document is not None:
        check_document_sources(conn, document)
    cursor = conn.execute(
        "SELECT k.*, s.payload_json AS score_payload, a.themes_json AS analysis_themes "
        "FROM knowledge_objects k LEFT JOIN importance_scores s ON s.knowledge_id=k.id "
        "LEFT JOIN content_analyses a ON a.knowledge_id=k.id "
        "WHERE k.deleted_at IS NULL AND julianday(COALESCE(k.published_at,k.fetched_at)) "
        "BETWEEN julianday(?) - 1.0/86400 AND julianday(?) + 1.0/86400 ORDER BY k.id",
        (start, end),
    )
    names = [column[0] for column in cursor.description]
    lower, upper = datetime.fromisoformat(start), datetime.fromisoformat(end)
    candidates = []
    for values in cursor.fetchall():
        row = dict(zip(names, values))
        instant = datetime.fromisoformat(row["published_at"] or row["fetched_at"])
        if instant.utcoffset() is None:
            instant = instant.replace(tzinfo=timezone.utc)
        if not lower <= instant < upper:
            continue
        score = row.pop("score_payload")
        themes = row.pop("analysis_themes")
        row.pop("deleted_at")
        row["metadata"] = json.loads(row.pop("metadata_json"))
        candidates.append(
            {
                "item": row,
                "score": json.loads(score) if score else None,
                "themes": json.loads(themes) if themes is not None else None,
            }
        )
    result = {"document": document, "candidates": candidates}
    return {**result, "fingerprint": hashlib.sha256(encode(result).encode()).hexdigest()}


def save_document(conn: sqlite3.Connection, document: dict[str, Any]) -> None:
    """Replace only with a newer refinement; identical saves are idempotent."""
    check_document_sources(conn, document)
    old = conn.execute(
        "SELECT refined_at, payload_json FROM intelligence_documents WHERE report_date=?",
        (document["date"],),
    ).fetchone()
    payload = encode(document)
    if old and old[1] == payload:
        return
    if old and datetime.fromisoformat(old[0]) >= datetime.fromisoformat(document["refined_at"]):
        raise ValueError("Cannot replace an equal-time or newer refined document")
    conn.execute(
        "INSERT INTO intelligence_documents VALUES (?, ?, ?, ?) "
        "ON CONFLICT(report_date) DO UPDATE SET document_id=excluded.document_id, "
        "refined_at=excluded.refined_at, payload_json=excluded.payload_json",
        (document["date"], document["document_id"], document["refined_at"], payload),
    )


def save_digest(
    conn: sqlite3.Connection,
    record: dict[str, Any],
    *,
    start: str,
    end: str,
    fingerprint: str,
    rebuild: bool,
    expected_id: str | None,
) -> dict[str, Any]:
    """First ordinary writer wins; explicit rebuild uses compare-and-swap."""
    date = record["digest_date"]
    old = conn.execute(
        "SELECT digest_id, payload_json FROM daily_digests WHERE digest_date=?",
        (date,),
    ).fetchone()
    if old and not rebuild:
        return json.loads(old[1])  # type: ignore[no-any-return]
    if (old[0] if old else None) != expected_id:
        raise RuntimeError("Digest changed during generation; reload before rebuilding")
    if load_inputs(conn, date, start, end)["fingerprint"] != fingerprint:
        raise RuntimeError("Digest prerequisites changed during generation; retry")
    conn.execute(
        "INSERT INTO daily_digests VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(digest_date) DO UPDATE SET digest_id=excluded.digest_id, "
        "generated_at=excluded.generated_at, total_items=excluded.total_items, "
        "sections_json=excluded.sections_json, topic_groups_json=excluded.topic_groups_json, "
        "document_id=excluded.document_id, payload_json=excluded.payload_json",
        (
            record["digest_id"],
            date,
            record["generated_at"],
            record["total_items"],
            encode(record["sections"]),
            encode(record["topic_groups"]),
            record["intelligence"]["document_id"],
            encode(record),
        ),
    )
    return record
