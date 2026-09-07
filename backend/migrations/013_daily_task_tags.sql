-- User-defined labels on daily plan tasks (separate from priority urgency).
ALTER TABLE daily_task
    ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb;
