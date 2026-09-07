"""SQLite schema definitions for Knowledge Repository storage.

Defines the DDL () for the knowledge_objects table and associated indexes.
This module is the single source of truth for the SQLite schema.
"""

# =============================================================================
# Table: knowledge_objects
# =============================================================================

KNOWLEDGE_OBJECTS_DDL = """
CREATE TABLE IF NOT EXISTS knowledge_objects (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    external_id TEXT,
    content_hash TEXT NOT NULL,
    source_url TEXT,
    title TEXT,
    content_text TEXT,
    metadata_json TEXT,
    fetched_at TIMESTAMP,
    published_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    parser_version TEXT DEFAULT '1.0.0',
    normalizer_version TEXT DEFAULT '1.0.0',
    extractor_version TEXT DEFAULT '1.0.0'
);
"""

# =============================================================================
# Indexes
# =============================================================================

# Identity lookup for idempotent upsert (DATA-001)
IDX_IDENTITY_DDL = """
CREATE INDEX IF NOT EXISTS idx_knowledge_identity
ON knowledge_objects(source_type, source_name, external_id);
"""

# Content hash lookup for dedup
IDX_CONTENT_HASH_DDL = """
CREATE INDEX IF NOT EXISTS idx_knowledge_content_hash
ON knowledge_objects(content_hash);
"""

# Source filtering
IDX_SOURCE_IDENTITY_DDL = """
CREATE INDEX IF NOT EXISTS idx_source_identity
ON knowledge_objects(source_type, source_name);
"""

# Time-based queries
IDX_PUBLISHED_AT_DDL = """
CREATE INDEX IF NOT EXISTS idx_published_at
ON knowledge_objects(published_at);
"""

IDX_CREATED_AT_DDL = """
CREATE INDEX IF NOT EXISTS idx_created_at
ON knowledge_objects(created_at);
"""

IDX_UPDATED_AT_DDL = """
CREATE INDEX IF NOT EXISTS idx_updated_at
ON knowledge_objects(updated_at);
"""

# Composite: latest from source
IDX_RECENT_BY_SOURCE_DDL = """
CREATE INDEX IF NOT EXISTS idx_recent_by_source
ON knowledge_objects(source_type, source_name, published_at DESC);
"""

# =============================================================================
# All DDL statements in execution order
# =============================================================================

ALL_DDL_STATEMENTS: list[str] = [
    KNOWLEDGE_OBJECTS_DDL,
    IDX_IDENTITY_DDL,
    IDX_CONTENT_HASH_DDL,
    IDX_SOURCE_IDENTITY_DDL,
    IDX_PUBLISHED_AT_DDL,
    IDX_CREATED_AT_DDL,
    IDX_UPDATED_AT_DDL,
    IDX_RECENT_BY_SOURCE_DDL,
]
