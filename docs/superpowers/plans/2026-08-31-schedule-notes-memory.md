# Schedule date filter, notes & memory — Implementation Plan

> **For agentic workers:** Implement inline task-by-task.

**Goal:** Date filter + day overview; per-task notes/docs and agent memories with prompt injection.

**Architecture:** New tables + nested CRUD APIs; Schedule UI date bar + overview + two panels; `start_task_workflow` appends notes/memories to prompt.

**Tech Stack:** FastAPI, SQLAlchemy, Postgres, React

---

### Task 1: Migration + models + schemas + service/API
### Task 2: Schedule UI — date filter + overview
### Task 3: Schedule UI — notes + memories panels
### Task 4: Inject into start_task_workflow; verify; weekly log
