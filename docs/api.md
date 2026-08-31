# REST & SSE API

Base URL: `/api/v1`  
认证：第一版省略，预留 `Authorization: Bearer`  
所有时间字段 ISO 8601 UTC。

---

## Provider 管理

| Method | Path | 说明 |
|--------|------|------|
| GET | `/providers` | 列表 |
| POST | `/providers` | 创建 |
| GET | `/providers/{id}` | 详情 |
| PATCH | `/providers/{id}` | 更新 |
| DELETE | `/providers/{id}` | 删除 |
| POST | `/providers/{id}/test` | 测试连接 |

**POST /providers** body:
```json
{
  "kind": "codex_cli",
  "type": "coding_agent",
  "name": "Codex Local",
  "endpoint": "codex",
  "default_model": "default",
  "config": { "api_key_ref": "env:OPENAI_API_KEY" },
  "capabilities": ["读写代码", "执行命令"]
}
```

---

## Agent 管理

| Method | Path | 说明 |
|--------|------|------|
| GET | `/agents` | 列表 |
| POST | `/agents` | 创建 |
| GET | `/agents/{id}` | 详情 |
| PATCH | `/agents/{id}` | 更新 |
| DELETE | `/agents/{id}` | 删除 |
| GET | `/agents/roles/templates` | 角色模板 Planner/Developer/… |

**POST /agents** body:
```json
{
  "name": "codex-backend",
  "provider_id": "prv_xxx",
  "model": "default",
  "role": "developer",
  "workspace_path": "/projects/demo/backend",
  "permissions": {
    "read_files": true,
    "write_files": true,
    "run_commands": true,
    "run_tests": true,
    "network": false
  },
  "limits": { "timeout_minutes": 30, "max_rounds": 5 },
  "streaming": true
}
```

---

## 工作流

| Method | Path | 说明 |
|--------|------|------|
| GET | `/workflows/definitions` | 工作流模板列表 |
| POST | `/workflows/definitions` | 创建模板 |
| GET | `/workflows/definitions/{id}` | 含 steps DAG |
| GET | `/workflows/runs` | 运行实例列表（?status=running） |
| POST | `/workflows/runs` | 启动工作流 |
| GET | `/workflows/runs/{id}` | 详情 + steps 状态（BPM 用） |
| POST | `/workflows/runs/{id}/pause` | 暂停 |
| POST | `/workflows/runs/{id}/resume` | 继续 |
| POST | `/workflows/runs/{id}/cancel` | 取消 |

**POST /workflows/runs** body:
```json
{
  "workflow_definition_id": "wfd_feature_dev",
  "daily_task_id": "tsk_xxx",
  "input": { "goal": "完成登录功能" }
}
```

**GET /workflows/runs/{id}** 响应（对齐前端 BPM）:
```json
{
  "id": "wfr_xxx",
  "name": "feature-development",
  "title": "登录功能开发",
  "status": "running",
  "progress": 42,
  "steps": [
    {
      "id": "planning",
      "label": "任务规划",
      "agent_name": "openai-planner",
      "provider": "OpenAI",
      "depends_on": [],
      "status": "completed",
      "run_id": "run_101",
      "parallel": false
    }
  ]
}
```

---

## Run 监控

| Method | Path | 说明 |
|--------|------|------|
| GET | `/runs` | 列表 ?status=running&workflow_run_id= |
| GET | `/runs/{run_id}` | Run 详情 |
| GET | `/runs/{run_id}/events` | 事件历史（分页） |
| GET | `/runs/{run_id}/messages` | 对话记录 |
| GET | `/runs/{run_id}/files` | 文件变更 |
| **POST** | **`/runs/{run_id}/messages`** | **运行中纠正指令** |
| POST | `/runs/{run_id}/pause` | |
| POST | `/runs/{run_id}/resume` | |
| POST | `/runs/{run_id}/cancel` | |
| POST | `/runs/{run_id}/approve` | 审批节点通过 |

**POST /runs/{run_id}/messages** body:
```json
{
  "content": "先不要改 router，只改 LoginView",
  "interrupt_current": true
}
```

响应：202 Accepted，后续事件经 SSE 推送。

---

## 实时事件 SSE

| Method | Path | 说明 |
|--------|------|------|
| GET | `/events/stream` | SSE 订阅 |

Query:
- `run_id=` 单 Agent Run
- `workflow_run_id=` 整个工作流
- `Last-Event-ID=` 断线重连

Event type: `agent_event`  
Data: AgentEvent JSON（与架构文档一致）

```
event: agent_event
data: {"run_id":"run_123","type":"file_changed",...}

event: heartbeat
data: {}
```

---

## 今日计划

| Method | Path | 说明 |
|--------|------|------|
| GET | `/schedule/tasks` | 今日清单 ?date=2026-08-27 |
| POST | `/schedule/tasks` | 手动添加 |
| GET | `/schedule/tasks/{id}` | 含 plan_items 详细计划 |
| PATCH | `/schedule/tasks/{id}` | 更新状态/标题 |
| DELETE | `/schedule/tasks/{id}` | 删除 |
| **POST** | **`/schedule/tasks/plan-today`** | **AI 规划今日（自然语言）** |
| POST | `/schedule/tasks/{id}/regenerate-plan` | AI 重新生成详细计划 |
| POST | `/schedule/tasks/{id}/start-workflow` | dev 任务触发工作流 |

**POST /schedule/tasks** body（快速添加）:
```json
{
  "title": "整理周报",
  "type": "normal",
  "priority": "medium"
}
```

**POST /schedule/tasks/plan-today** body:
```json
{
  "goal": "今天完成登录功能，下午 review PR #128",
  "auto_start_dev_workflows": true
}
```

响应：创建的 `daily_task[]` + 每个任务的 `plan_items`（异步时可 202 + task_id 轮询）

**GET /schedule/tasks/{id}** 响应:
```json
{
  "id": "tsk_xxx",
  "title": "完成登录功能",
  "type": "dev",
  "status": "in_progress",
  "summary": "...",
  "plan_author": "openai-planner",
  "plan_updated_at": "...",
  "workflow_definition_id": "wfd_feature_dev",
  "plan_items": [
    {
      "id": "tpl_1",
      "scheduled_time": "09:30",
      "title": "Codex 实现后端",
      "detail": "...",
      "status": "in_progress",
      "agent_id": "agt_codex",
      "linked_step_key": "backend"
    }
  ]
}
```

---

## 错误格式

```json
{
  "error": {
    "code": "RUN_NOT_RUNNING",
    "message": "无法注入消息：Run 未处于 running 状态"
  }
}
```

| HTTP | code |
|------|------|
| 400 | VALIDATION_ERROR |
| 404 | NOT_FOUND |
| 409 | RUN_NOT_RUNNING / WORKFLOW_ALREADY_STARTED |
| 502 | PROVIDER_ERROR |

---

## 前端页面对照

| 原型页面 | 主要 API |
|----------|----------|
| Provider 管理 | `/providers` |
| Agent 管理 | `/agents` |
| 工作流 BPM | `/workflows/runs/{id}` + SSE |
| 运行监控 | `/workflows/runs` + `/runs/{id}` + SSE |
| 今日计划 | `/schedule/tasks` + `/plan-today` |
| 纠正指令 | `POST /runs/{id}/messages` |
