# Schedule: date filter, overview, notes & memory

**Date:** 2026-08-31  
**Status:** approved  
**Repos:** agent-forge backend + agent-orchestrator-prototype Schedule

## Goals

1. Filter daily tasks by date; show day-level completion overview.
2. Per-task human notes/docs (`task_note`).
3. Per-task agent memory (`task_memory`), injected on workflow start.

## §1 Date filter + overview

- UI: date picker (default today) + “今天” shortcut.
- `GET /schedule/tasks?plan_date=YYYY-MM-DD` (existing).
- Overview bar for selected day: task counts by status; step completion `sum(plan_done)/sum(plan_item_count)`.
- Optional: `GET /schedule/overview?plan_date=` returning aggregates (can also compute client-side from list).

## §2 Notes + memory

### `task_note`
- `id`, `daily_task_id`, `kind` (`markdown`|`file`), `title`, `body`, `file_path`, `created_at`, `updated_at`
- CRUD under `/schedule/tasks/{task_id}/notes`

### `task_memory`
- `id`, `daily_task_id`, `content`, `tags` (JSONB list), `pinned` bool, `created_at`, `updated_at`
- CRUD under `/schedule/tasks/{task_id}/memories`

Cascade delete with daily_task.

### Start workflow prompt order
1. explicit `task_prompt` if any  
2. `requirement`  
3. pinned memories then other memories (truncated)  
4. notes: markdown bodies (truncate) + file paths  
5. fallback `summary` / `title`

## UI

Schedule detail below「任务要求」:
- Notes & docs panel
- Agent memory panel

## Out of scope

- Binary file upload / object storage (path-only for files)
- Cross-task shared memory
- Vector/RAG search
