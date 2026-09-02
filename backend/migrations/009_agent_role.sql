-- Agent role catalog (configurable; used by Agent + Workflow steps).
CREATE TABLE IF NOT EXISTS agent_role (
    id                      TEXT PRIMARY KEY,
    code                    TEXT NOT NULL UNIQUE,
    name                    TEXT NOT NULL,
    description             TEXT NOT NULL DEFAULT '',
    system_prompt           TEXT NOT NULL DEFAULT '',
    default_provider_kind   TEXT NOT NULL DEFAULT '',
    sort_order              INTEGER NOT NULL DEFAULT 0,
    is_builtin              BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_role_sort ON agent_role (sort_order, code);
