-- Per-task human notes/docs and agent memory entries.
CREATE TABLE IF NOT EXISTS task_note (
    id              TEXT PRIMARY KEY,
    daily_task_id   TEXT NOT NULL REFERENCES daily_task(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL DEFAULT 'markdown',
    title           TEXT NOT NULL DEFAULT '',
    body            TEXT NOT NULL DEFAULT '',
    file_path       TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_task_note_task ON task_note (daily_task_id, created_at);

CREATE TABLE IF NOT EXISTS task_memory (
    id              TEXT PRIMARY KEY,
    daily_task_id   TEXT NOT NULL REFERENCES daily_task(id) ON DELETE CASCADE,
    content         TEXT NOT NULL DEFAULT '',
    tags            JSONB NOT NULL DEFAULT '[]',
    pinned          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_task_memory_task ON task_memory (daily_task_id, pinned DESC, created_at);
