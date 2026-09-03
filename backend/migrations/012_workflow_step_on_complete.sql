-- Per-step completion policy: none | notify | confirm
ALTER TABLE workflow_step_def
    ADD COLUMN IF NOT EXISTS on_complete TEXT NOT NULL DEFAULT 'none';

UPDATE workflow_step_def
SET on_complete = 'none'
WHERE on_complete IS NULL OR on_complete = '';
