-- Persist user-authored detailed requirements separately from system summary.
ALTER TABLE daily_task
    ADD COLUMN IF NOT EXISTS requirement TEXT NOT NULL DEFAULT '';

-- Backfill: prefer existing summary when requirement is still empty.
UPDATE daily_task
SET requirement = summary
WHERE (requirement IS NULL OR requirement = '')
  AND summary IS NOT NULL
  AND summary <> '';
