"""Email DDL; EmailStore initializes these tables in the repository database."""

EMAIL_DDL = """
CREATE TABLE IF NOT EXISTS subscribers (
    email TEXT PRIMARY KEY,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
    soft_bounces INTEGER NOT NULL DEFAULT 0 CHECK(soft_bounces >= 0),
    inactive_reason TEXT,
    created_at TEXT NOT NULL,
    unsubscribe_token TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS email_events (
    email TEXT NOT NULL,
    message_id TEXT NOT NULL,
    event TEXT NOT NULL,
    received_at TEXT NOT NULL,
    PRIMARY KEY(email, message_id, event)
);
CREATE TABLE IF NOT EXISTS email_deliveries (
    digest_id TEXT NOT NULL,
    email TEXT NOT NULL,
    attempt_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('sending','accepted','failed','unknown')),
    message_id TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(digest_id, email)
);
"""
