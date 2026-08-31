-- Tag plan items with the workflow template they belong to (multi-plan tables per task).
ALTER TABLE task_plan_item
    ADD COLUMN IF NOT EXISTS workflow_definition_id TEXT REFERENCES workflow_definition(id);

-- Backfill from the task's active workflow when possible.
UPDATE task_plan_item tpi
SET workflow_definition_id = dt.workflow_definition_id
FROM daily_task dt
WHERE tpi.daily_task_id = dt.id
  AND tpi.workflow_definition_id IS NULL
  AND dt.workflow_definition_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_task_plan_item_wf
    ON task_plan_item (daily_task_id, workflow_definition_id);
