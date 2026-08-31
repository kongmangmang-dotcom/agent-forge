-- AgentForge initial schema
-- PostgreSQL 15+

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ========== Provider & Agent ==========

CREATE TABLE provider (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('model_api', 'coding_agent', 'local_runtime')),
    name            TEXT NOT NULL,
    endpoint        TEXT NOT NULL DEFAULT '',
    default_model   TEXT NOT NULL DEFAULT '',
    config_encrypted JSONB NOT NULL DEFAULT '{}',
    capabilities    JSONB NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'disconnected',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE agent (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    provider_id     TEXT NOT NULL REFERENCES provider(id),
    model           TEXT NOT NULL DEFAULT '',
    role            TEXT NOT NULL,
    system_prompt   TEXT NOT NULL DEFAULT '',
    workspace_path  TEXT NOT NULL DEFAULT '',
    permissions     JSONB NOT NULL DEFAULT '{}',
    limits          JSONB NOT NULL DEFAULT '{}',
    streaming       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ========== Workflow ==========

CREATE TABLE workflow_definition (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    options         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE workflow_step_def (
    id              TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL REFERENCES workflow_definition(id) ON DELETE CASCADE,
    step_key        TEXT NOT NULL,
    label           TEXT NOT NULL,
    agent_id        TEXT NOT NULL REFERENCES agent(id),
    depends_on      JSONB NOT NULL DEFAULT '[]',
    parallel        BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order      INT NOT NULL DEFAULT 0,
    UNIQUE (workflow_id, step_key)
);

CREATE TABLE workflow_run (
    id              TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL REFERENCES workflow_definition(id),
    daily_task_id   TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    progress        INT NOT NULL DEFAULT 0,
    input           JSONB NOT NULL DEFAULT '{}',
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE step_run (
    id              TEXT PRIMARY KEY,
    workflow_run_id TEXT NOT NULL REFERENCES workflow_run(id) ON DELETE CASCADE,
    step_key        TEXT NOT NULL,
    agent_id        TEXT NOT NULL REFERENCES agent(id),
    status          TEXT NOT NULL DEFAULT 'pending',
    progress        INT NOT NULL DEFAULT 0,
    agent_run_id    TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    UNIQUE (workflow_run_id, step_key)
);

-- ========== Agent Run ==========

CREATE TABLE agent_run (
    id              TEXT PRIMARY KEY,
    step_run_id     TEXT REFERENCES step_run(id),
    agent_id        TEXT NOT NULL REFERENCES agent(id),
    status          TEXT NOT NULL DEFAULT 'pending',
    task_prompt     TEXT NOT NULL DEFAULT '',
    workspace_path  TEXT NOT NULL DEFAULT '',
    tokens_used     INT NOT NULL DEFAULT 0,
    command_output  TEXT,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE step_run
    ADD CONSTRAINT fk_step_run_agent_run
    FOREIGN KEY (agent_run_id) REFERENCES agent_run(id);

CREATE TABLE agent_event (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES agent_run(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'completed',
    content         TEXT NOT NULL DEFAULT '',
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_event_run_time ON agent_event (run_id, created_at);

CREATE TABLE agent_message (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES agent_run(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    tool_calls      JSONB,
    streaming       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_message_run ON agent_message (run_id, created_at);

CREATE TABLE file_change (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES agent_run(id) ON DELETE CASCADE,
    path            TEXT NOT NULL,
    action          TEXT NOT NULL,
    lines_summary   TEXT NOT NULL DEFAULT '',
    diff            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_file_change_run ON file_change (run_id);

-- ========== Schedule ==========

CREATE TABLE daily_task (
    id                      TEXT PRIMARY KEY,
    plan_date               DATE NOT NULL DEFAULT CURRENT_DATE,
    title                   TEXT NOT NULL,
    type                    TEXT NOT NULL DEFAULT 'normal' CHECK (type IN ('normal', 'dev')),
    status                  TEXT NOT NULL DEFAULT 'todo',
    priority                TEXT NOT NULL DEFAULT 'medium',
    summary                 TEXT NOT NULL DEFAULT '',
    workflow_definition_id  TEXT REFERENCES workflow_definition(id),
    plan_author             TEXT,
    plan_updated_at         TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_daily_task_date ON daily_task (plan_date, status);

CREATE TABLE task_plan_item (
    id                  TEXT PRIMARY KEY,
    daily_task_id       TEXT NOT NULL REFERENCES daily_task(id) ON DELETE CASCADE,
    sort_order          INT NOT NULL DEFAULT 0,
    scheduled_time      TEXT,
    title               TEXT NOT NULL,
    detail              TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'todo',
    agent_id            TEXT REFERENCES agent(id),
    linked_step_key     TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE workflow_run
    ADD CONSTRAINT fk_workflow_run_daily_task
    FOREIGN KEY (daily_task_id) REFERENCES daily_task(id);

-- ========== Helpers ==========

CREATE OR REPLACE FUNCTION gen_prefixed_id(prefix TEXT)
RETURNS TEXT AS $$
    SELECT prefix || '_' || encode(gen_random_bytes(8), 'hex');
$$ LANGUAGE SQL;
