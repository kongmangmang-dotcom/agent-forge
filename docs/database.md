# 数据库设计

PostgreSQL 15+。主键使用 `text` 前缀 ID（`prv_`, `agt_`, `wfd_`, `wfr_`, `run_`）。

## ER 关系概览

```
provider ──< agent
workflow_definition ──< workflow_step_def
workflow_definition ──< workflow_run ──< step_run ──< agent_run
agent_run ──< agent_event
agent_run ──< agent_message
agent_run ──< file_change
daily_task ──< task_plan_item
daily_task ──o workflow_run   (可选关联)
```

## 表定义

### provider

| 列 | 类型 | 说明 |
|----|------|------|
| id | text PK | prv_xxx |
| kind | text | openai / anthropic / gemini / codex_cli / opencode_cli |
| type | text | model_api / coding_agent / local_runtime |
| name | text | 显示名 |
| endpoint | text | API URL 或 CLI 命令 |
| default_model | text | |
| config_encrypted | jsonb | API key 等（加密存储） |
| capabilities | jsonb | string[] |
| status | text | connected / disconnected / error |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### agent

| 列 | 类型 | 说明 |
|----|------|------|
| id | text PK | agt_xxx |
| name | text UNIQUE | openai-planner |
| provider_id | text FK | |
| model | text | |
| role | text | planner / researcher / developer / … |
| system_prompt | text | |
| workspace_path | text | 项目根目录 |
| permissions | jsonb | read_files, write_files, … |
| limits | jsonb | timeout_minutes, max_rounds |
| streaming | boolean | |
| created_at | timestamptz | |

### workflow_definition

| 列 | 类型 | 说明 |
|----|------|------|
| id | text PK | wfd_xxx |
| name | text UNIQUE | feature-development |
| title | text | 登录功能开发 |
| description | text | |
| options | jsonb | 允许联网、审批、重试等 |
| created_at | timestamptz | |

### workflow_step_def

| 列 | 类型 | 说明 |
|----|------|------|
| id | text PK | wfs_xxx |
| workflow_id | text FK | |
| step_key | text | planning, backend, … |
| label | text | 任务规划 |
| agent_id | text FK | |
| depends_on | jsonb | string[] step_key |
| parallel | boolean | 同层可并行 |
| sort_order | int | |
| UNIQUE(workflow_id, step_key) | | |

### workflow_run

| 列 | 类型 | 说明 |
|----|------|------|
| id | text PK | wfr_xxx |
| workflow_id | text FK | |
| daily_task_id | text FK NULL | 来自今日计划 |
| status | text | pending/running/completed/failed/paused |
| progress | int | 0-100 |
| started_at | timestamptz | |
| finished_at | timestamptz NULL | |
| error_message | text NULL | |

### step_run

| 列 | 类型 | 说明 |
|----|------|------|
| id | text PK | str_xxx |
| workflow_run_id | text FK | |
| step_key | text | |
| agent_id | text FK | |
| status | text | pending/running/completed/failed/waiting_approval |
| progress | int | |
| agent_run_id | text FK NULL | 当前关联 Run |
| started_at | timestamptz NULL | |
| finished_at | timestamptz NULL | |

### agent_run

| 列 | 类型 | 说明 |
|----|------|------|
| id | text PK | run_xxx |
| step_run_id | text FK NULL | |
| agent_id | text FK | |
| status | text | pending/running/completed/failed/paused/cancelled |
| task_prompt | text | 初始任务 |
| workspace_path | text | |
| tokens_used | int | 0 |
| started_at | timestamptz | |
| finished_at | timestamptz NULL | |
| command_output | text NULL | 最后一次命令输出 |

### agent_event

| 列 | 类型 | 说明 |
|----|------|------|
| id | bigserial PK | |
| run_id | text FK | |
| type | text | session_created, file_changed, … |
| status | text | running/completed/failed/waiting |
| content | text | |
| metadata | jsonb | |
| created_at | timestamptz | |

索引：`(run_id, created_at)`, `(run_id, type)`

### agent_message

| 列 | 类型 | 说明 |
|----|------|------|
| id | text PK | msg_xxx |
| run_id | text FK | |
| role | text | user/assistant/system/thinking |
| content | text | |
| tool_calls | jsonb NULL | |
| streaming | boolean | |
| created_at | timestamptz | |

### file_change

| 列 | 类型 | 说明 |
|----|------|------|
| id | bigserial PK | |
| run_id | text FK | |
| path | text | |
| action | text | created/modified/deleted |
| lines_summary | text | +42 -8 |
| diff | text NULL | |
| created_at | timestamptz | |

### daily_task

| 列 | 类型 | 说明 |
|----|------|------|
| id | text PK | tsk_xxx |
| plan_date | date | 默认 today |
| title | text | |
| type | text | normal / dev |
| status | text | todo / in_progress / done |
| priority | text | high/medium/low |
| summary | text | |
| workflow_definition_id | text FK NULL | dev 任务模板 |
| plan_author | text | openai-planner |
| plan_updated_at | timestamptz | |
| created_at | timestamptz | |

### task_plan_item

| 列 | 类型 | 说明 |
|----|------|------|
| id | text PK | tpl_xxx |
| daily_task_id | text FK | |
| sort_order | int | |
| scheduled_time | text NULL | 09:00 |
| title | text | |
| detail | text | |
| status | text | todo/in_progress/done |
| agent_id | text FK NULL | |
| linked_step_key | text NULL | 关联 workflow step |
| created_at | timestamptz | |

## 状态机

### agent_run.status

```
pending → running → completed
                 → failed
                 → paused → running
                 → cancelled
```

### workflow_run 进度

`progress = round(completed_steps / total_steps * 100)`

## 初始化 SQL

见 `backend/migrations/001_initial.sql`
