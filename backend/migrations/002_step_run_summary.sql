-- Add summary for completed workflow steps (injected into downstream prompts).
ALTER TABLE step_run
    ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT '';
