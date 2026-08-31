-- Link standalone AgentRuns to a DailyTask (direct agent chat).
ALTER TABLE agent_run
    ADD COLUMN IF NOT EXISTS daily_task_id TEXT REFERENCES daily_task(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_agent_run_daily_task
    ON agent_run (daily_task_id, agent_id, created_at DESC);
