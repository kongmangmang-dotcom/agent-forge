-- Per-step role assignment (workflow-time role; agent.role may be empty).
ALTER TABLE workflow_step_def
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT '';
