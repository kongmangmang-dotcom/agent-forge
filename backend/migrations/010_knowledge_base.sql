-- Simplified RAG knowledge base (single-tenant; no SolarSense tenant/quota/RBAC).
CREATE TABLE IF NOT EXISTS knowledge_base (
    id                      TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    description             TEXT NOT NULL DEFAULT '',
    embedding_model         TEXT NOT NULL DEFAULT '',
    top_k                   INTEGER NOT NULL DEFAULT 5,
    similarity_threshold    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    status                  TEXT NOT NULL DEFAULT 'active',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_document (
    id                      TEXT PRIMARY KEY,
    knowledge_id            TEXT NOT NULL REFERENCES knowledge_base(id) ON DELETE CASCADE,
    name                    TEXT NOT NULL,
    content                 TEXT NOT NULL DEFAULT '',
    content_length          INTEGER NOT NULL DEFAULT 0,
    segment_max_chars       INTEGER NOT NULL DEFAULT 800,
    status                  TEXT NOT NULL DEFAULT 'indexed',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_document_kb
    ON knowledge_document (knowledge_id);

CREATE TABLE IF NOT EXISTS knowledge_segment (
    id                      TEXT PRIMARY KEY,
    knowledge_id            TEXT NOT NULL REFERENCES knowledge_base(id) ON DELETE CASCADE,
    document_id             TEXT NOT NULL REFERENCES knowledge_document(id) ON DELETE CASCADE,
    content                 TEXT NOT NULL,
    content_length          INTEGER NOT NULL DEFAULT 0,
    embedding               JSONB,
    status                  TEXT NOT NULL DEFAULT 'active',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_segment_kb
    ON knowledge_segment (knowledge_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_segment_doc
    ON knowledge_segment (document_id);
