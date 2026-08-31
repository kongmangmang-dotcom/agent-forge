# Daily Task requirement field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or implement inline task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist user requirements on daily tasks; show/edit them after plan generation; prefer them when starting workflows.

**Architecture:** Add `daily_task.requirement` (migration + model/schema/service). Schedule UI: create with requirement-only for plan-today; detail card above workflow config for title + requirement edit/save.

**Tech Stack:** FastAPI, SQLAlchemy async, Postgres, React + Vite (Schedule.tsx)

## Global Constraints

- Never overwrite `requirement` when regenerating plan items
- Prompt order for start workflow: explicit arg → requirement → summary → title
- Title v1 = truncate/first-line of requirement (~80 chars); no LLM title call
- Plan steps still come from workflow template DAG

---

### Task 1: Migration + model + schemas + service

**Files:**
- Create: `D:\agent-forge\backend\migrations\003_daily_task_requirement.sql`
- Modify: `D:\agent-forge\backend\app\models\schedule.py`
- Modify: `D:\agent-forge\backend\app\schemas\schedule.py`
- Modify: `D:\agent-forge\backend\app\services\schedule_service.py`

- [ ] **Step 1:** Add migration SQL with column + optional backfill from summary
- [ ] **Step 2:** Add `requirement` on model, create/update/read/summary schemas
- [ ] **Step 3:** Wire create/update/read/plan_today/start_task_workflow/_replace_plan_items per design
- [ ] **Step 4:** Apply migration against local Postgres (`localhost:5434`)

### Task 2: Frontend API + Schedule UI

**Files:**
- Modify: `D:\agent-orchestrator-prototype\src\api\schedule.ts`
- Modify: `D:\agent-orchestrator-prototype\src\pages\Schedule.tsx`

- [ ] **Step 1:** Add `requirement` to types and create/update payloads
- [ ] **Step 2:** AI plan form: requirement textarea; optional empty title (backend derives)
- [ ] **Step 3:** Detail: editable title + requirement card above workflow config; Save via PATCH
- [ ] **Step 4:** Prefill empty requirement from summary/title in editor only

### Task 3: Verify

- [ ] Apply migration; restart backend if needed
- [ ] Create plan with requirement → open task → see requirement → edit/save → reload persists
- [ ] Regenerate plan → requirement unchanged
- [ ] Append weekly dev summary
