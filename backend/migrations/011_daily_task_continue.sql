-- Cross-day task continuation lineage.
ALTER TABLE daily_task
    ADD COLUMN IF NOT EXISTS continued_from_id VARCHAR REFERENCES daily_task(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS continued_to_id VARCHAR REFERENCES daily_task(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_daily_task_continued_from ON daily_task(continued_from_id);
CREATE INDEX IF NOT EXISTS idx_daily_task_continued_to ON daily_task(continued_to_id);
