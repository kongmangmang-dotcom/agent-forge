-- Bound workflow templates per daily task (active template remains workflow_definition_id).
ALTER TABLE daily_task
    ADD COLUMN IF NOT EXISTS bound_workflow_ids JSONB NOT NULL DEFAULT '[]'::jsonb;

UPDATE daily_task
SET bound_workflow_ids = jsonb_build_array(workflow_definition_id)
WHERE workflow_definition_id IS NOT NULL
  AND (
    bound_workflow_ids IS NULL
    OR bound_workflow_ids = '[]'::jsonb
    OR jsonb_typeof(bound_workflow_ids) <> 'array'
  );
