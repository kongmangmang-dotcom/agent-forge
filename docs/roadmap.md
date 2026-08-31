# 实现路线图

与前端原型页面对齐的交付顺序。

## M1 — 基础 CRUD + 单 Run（2 周）

- [ ] PostgreSQL + SQLAlchemy async 模型
- [ ] Provider / Agent CRUD
- [ ] WorkflowDefinition + StepDef CRUD
- [ ] 单 Agent Run：OpenAI Provider 实现
- [ ] agent_event / agent_message 持久化
- [ ] SSE `/events/stream?run_id=`
- [ ] 前端 mock → 接真实 API

## M2 — Orchestrator + DAG（2 周）

- [ ] `OrchestratorService.start_workflow`
- [ ] DAG 拓扑调度 + 并行 step
- [ ] StepRun / WorkflowRun 状态机
- [ ] Codex CLI Provider（subprocess + 事件解析）
- [ ] OpenCode CLI Provider
- [ ] `POST /runs/{id}/messages` 纠正指令
- [ ] BPM 页 `GET /workflows/runs/{id}`

## M3 — 今日计划（1 周）

- [ ] DailyTask + TaskPlanItem CRUD
- [ ] `POST /schedule/tasks/plan-today` → Planner Agent
- [ ] dev 任务自动 `start-workflow`
- [ ] Step 完成 → 回写 plan_item.status
- [ ] `regenerate-plan`

## M4 — 生产增强（按需）

- [ ] 审批节点 `waiting_approval`
- [ ] Redis Pub/Sub 多实例 SSE
- [ ] Provider 密钥加密（Vault / env ref）
- [ ] Temporal 替换自研调度（可选）
- [ ] Anthropic / Gemini Provider

## 前端联调清单

| 页面 | 接口 |
|------|------|
| Provider 管理 | GET/POST `/providers` |
| Agent 管理 | GET/POST `/agents` |
| 工作流 BPM | GET `/workflows/runs/{id}` |
| 运行监控 | BPM + GET `/runs/{id}` + SSE |
| 今日计划 | GET/POST `/schedule/tasks` |
| 纠正指令 | POST `/runs/{id}/messages` |
