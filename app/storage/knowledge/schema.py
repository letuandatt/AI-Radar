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
    fetched_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    parser_version TEXT DEFAULT '1.0.0',
    normalizer_version TEXT DEFAULT '1.0.0',
    extractor_version TEXT DEFAULT '1.0.0',
    deleted_at TIMESTAMP NULL DEFAULT NULL
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
# Create table for LLM logs
# =============================================================================

CREATE_LLM_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS llm_logs (
    log_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt TEXT,
    response TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    latency_ms REAL,
    cost_usd REAL,
    status TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    prompt_name TEXT,
    prompt_version TEXT,
    created_at TIMESTAMP NOT NULL
);
"""

IDX_LLM_LOGS_CREATED_AT_DDL = """
CREATE INDEX IF NOT EXISTS idx_llm_logs_created_at 
ON llm_logs(created_at);
"""

# =============================================================================
# Content Analysis Results
# =============================================================================

CREATE_CONTENT_ANALYSES_TABLE = """
CREATE TABLE IF NOT EXISTS content_analyses (
    analysis_id TEXT PRIMARY KEY,
    knowledge_id TEXT NOT NULL,
    analyzed_at TIMESTAMP NOT NULL,
    themes_json TEXT NOT NULL,
    entities_json TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    key_claims_json TEXT NOT NULL,
    technical_depth TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (knowledge_id) REFERENCES knowledge_objects(id)
);
"""

IDX_CONTENT_ANALYSES_CREATED_AT_DDL = """
CREATE INDEX IF NOT EXISTS idx_content_analyses_knowledge_id
ON content_analyses(knowledge_id);
"""

# =============================================================================
#
# =============================================================================

# Applied after legacy duplicate cleanup by SQLiteKnowledgeStore.
IDX_CONTENT_ANALYSES_IDENTITY_DDL = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_content_analyses_knowledge_id
ON content_analyses(knowledge_id);
"""

# =============================================================================
# All DDL statements in execution order
# =============================================================================

ALL_DDL_STATEMENTS: list[str] = [
    CREATE_LLM_LOGS_TABLE,
    IDX_LLM_LOGS_CREATED_AT_DDL,
    CREATE_CONTENT_ANALYSES_TABLE,
    IDX_CONTENT_ANALYSES_CREATED_AT_DDL,
    KNOWLEDGE_OBJECTS_DDL,
    IDX_IDENTITY_DDL,
    IDX_CONTENT_HASH_DDL,
    IDX_SOURCE_IDENTITY_DDL,
    IDX_PUBLISHED_AT_DDL,
    IDX_CREATED_AT_DDL,
    IDX_UPDATED_AT_DDL,
    IDX_RECENT_BY_SOURCE_DDL,
]
