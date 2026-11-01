"""Atomic subscriber and delivery records, using primitive values only."""

import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.storage.knowledge.email_schema import EMAIL_DDL


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EmailStore:
    """Short-lived connections allow CLI and async webhook threads to share SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError("Open an existing repository database")
        with self.connection() as conn:
            conn.executescript(EMAIL_DDL)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Serialize writes across processes; commit or roll back and always close."""
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
        finally:
            conn.close()

    def subscribe(self, email: str) -> dict[str, Any]:
        """Insert once without reactivating an existing opt-out or bounced address."""
        with self.connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO subscribers(email,created_at,unsubscribe_token) "
                "VALUES(?,?,?)",
                (email, now(), secrets.token_urlsafe(32)),
            )
            return dict(
                conn.execute("SELECT * FROM subscribers WHERE email=?", (email,)).fetchone()
            )

    def get(self, email: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM subscribers WHERE email=?", (email,)).fetchone()
            return dict(row) if row else None

    def active(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            return [
                dict(row)
                for row in conn.execute("SELECT * FROM subscribers WHERE active=1 ORDER BY email")
            ]

    def deactivate(self, email: str, reason: str) -> bool:
        with self.connection() as conn:
            return bool(
                conn.execute(
                    "UPDATE subscribers SET active=0, inactive_reason=? WHERE email=?",
                    (reason, email),
                ).rowcount
            )

    def unsubscribe(self, token: str) -> bool:
        with self.connection() as conn:
            return bool(
                conn.execute(
                    "UPDATE subscribers SET active=0,inactive_reason='unsubscribed' "
                    "WHERE unsubscribe_token=?",
                    (token,),
                ).rowcount
            )

    def event(self, email: str, message_id: str, event: str, limit: int) -> bool:
        """Count a bounce once per message; event receipt and suppression are atomic."""
        with self.connection() as conn:
            if not conn.execute("SELECT 1 FROM subscribers WHERE email=?", (email,)).fetchone():
                return False
            inserted = conn.execute(
                "INSERT OR IGNORE INTO email_events VALUES(?,?,?,?)",
                (email, message_id, event, now()),
            ).rowcount
            if not inserted:
                return False
            if event == "soft_bounce":
                conn.execute(
                    "UPDATE subscribers SET soft_bounces=soft_bounces+1 WHERE email=?", (email,)
                )
                conn.execute(
                    "UPDATE subscribers SET active=0,inactive_reason='soft_bounce_limit' "
                    "WHERE email=? AND active=1 AND soft_bounces>=?",
                    (email, limit),
                )
            else:
                conn.execute(
                    "UPDATE subscribers SET active=0,inactive_reason=? WHERE email=?",
                    (event, email),
                )
            return True

    def claim(self, digest_id: str, email: str) -> str | None:
        """Claim once; failed requests may retry, ambiguous or accepted ones may not."""
        with self.connection() as conn:
            if not conn.execute(
                "SELECT 1 FROM subscribers WHERE email=? AND active=1", (email,)
            ).fetchone():
                return None
            old = conn.execute(
                "SELECT status FROM email_deliveries WHERE digest_id=? AND email=?",
                (digest_id, email),
            ).fetchone()
            if old and old[0] != "failed":
                return None
            key = str(uuid4())
            conn.execute(
                "INSERT INTO email_deliveries VALUES(?,?,?,'sending',NULL,?) "
                "ON CONFLICT(digest_id,email) DO UPDATE SET attempt_key=excluded.attempt_key,"
                "status='sending',message_id=NULL,updated_at=excluded.updated_at",
                (digest_id, email, key, now()),
            )
            return key

    def finish(self, key: str, status: str, message_id: str | None) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE email_deliveries SET status=?,message_id=?,updated_at=? "
                "WHERE attempt_key=? AND status='sending'",
                (status, message_id, now(), key),
            )

    def delivery(self, digest_id: str, email: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM email_deliveries WHERE digest_id=? AND email=?", (digest_id, email)
            ).fetchone()
            return dict(row) if row else None
