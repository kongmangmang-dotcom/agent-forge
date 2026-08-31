# AgentForge 第一期实现计划（完整版）

> 版本：v1.0  
> 周期：**5–6 周**（可按 1 人全职估算；2 人可压缩至 3–4 周）  
> 仓库：`D:\agent-forge`（后端） + `D:\agent-orchestrator-prototype`（前端）  
> 目标：交付可演示、可联调的 **Agent 编排平台 MVP**，覆盖原型全部核心页面。

---

## 一、第一期要解决什么

构建一个**独立**的 Agent 编排平台，使用户能够：

1. 配置多种 AI Provider（模型 API + 编程 CLI）
2. 配置 Agent（角色、权限、工作区）
3. 定义并运行 **DAG 工作流**（多 Agent 协作、并行分支）
4. 在 **BPM 流程图** 上点击节点，查看 Agent 运行详情（对话、文件变更、日志）
5. 运行中 **发送纠正指令** 干预 Agent
6. 管理 **今日计划**：任务清单 → AI 详细计划 → 开发任务触发工作流 → 状态回写

**第一期不做：** 多租户、SSO、Cursor/Hermes 专用 Adapter、Temporal、与 SolarSense 集成。

---

## 二、第一期范围边界

### 2.1 纳入范围（Must Have）

| 类别 | 内容 |
|------|------|
| **Provider** | OpenAI、Anthropic、Gemini（HTTP API）；Codex CLI、OpenCode CLI（subprocess） |
| **配置** | Provider CRUD、Agent CRUD、Workflow 模板 CRUD |
| **编排** | 自研 DAG Orchestrator（依赖、并行、状态机） |
| **运行** | AgentRun、统一事件、SSE 推送、暂停/继续/取消 |
| **干预** | `POST /runs/{id}/messages` 纠正指令 |
| **协作 UI** | 工作流 BPM、运行监控（左 BPM + 右详情） |
| **日程** | 今日任务清单、AI 详细计划、dev 任务联动工作流 |
| **存储** | PostgreSQL 持久化；Redis 事件缓冲 / Run 状态 |
| **前端** | 原型页接真实 API（替换 mock） |

### 2.2 暂不纳入（Phase 2+）

| 类别 | 内容 |
|------|------|
| Provider | Cursor、Pi、Hermes、OpenClaw 专用 Adapter |
| 编排 | Temporal 替换自研调度 |
| 安全 | 密钥 Vault、多用户权限 |
| 运维 | 多实例 SSE 广播、K8s 部署手册 |
| 功能 | 人工审批完整 UI（可先留 `waiting_approval` 状态） |

---

## 三、技术栈（已定）

| 层 | 选型 |
|----|------|
| 后端语言 | Python 3.11+ |
| API | FastAPI + Pydantic v2 |
| ORM | SQLAlchemy 2.x async + asyncpg |
| 数据库 | PostgreSQL 16 |
| 缓存/队列 | Redis 7 |
| 实时 | SSE（`sse-starlette`） |
| 前端 | React + Vite + TypeScript（现有原型） |
| 部署 | Docker Compose（本地/dev） |

---

## 四、里程碑拆分（5 周）

```
Week 1 ── 基础设施 + 配置 CRUD
Week 2 ── 单 Agent Run + OpenAI Provider + SSE
Week 3 ── DAG Orchestrator + Workflow Run
Week 4 ── Codex/OpenCode Provider + 纠正指令 + BPM/监控联调
Week 5 ── 今日计划 + AI 规划 + 全链路验收
Week 6 ── 缓冲：Bugfix、文档、Seed 数据、演示环境
```

---

## 五、Week 1 — 基础设施与配置层

### 5.1 目标

数据库跑通，Provider / Agent / Workflow 模板可增删改查，API 文档可访问。

### 5.2 任务清单

#### 基础设施

- [ ] Docker Compose 启动 PostgreSQL + Redis + API
- [ ] 执行 `migrations/001_initial.sql`，确认表结构
- [ ] SQLAlchemy async engine + session 依赖注入
- [ ] 统一 ID 生成：`prv_` / `agt_` / `wfd_` / `run_` 等
- [ ] 全局异常处理 + 错误 JSON 格式（见 `docs/api.md`）
- [ ] CORS 配置（允许前端 `localhost:5173/5174`）
- [ ] 健康检查 `/health`

#### Provider 模块

- [ ] ORM `Provider` 模型
- [ ] `GET/POST/PATCH/DELETE /api/v1/providers`
- [ ] `POST /api/v1/providers/{id}/test`（Week 1 可先返回 mock，Week 2 接真连接）
- [ ] `ProviderRegistry` 注册机制骨架
- [ ] 密钥存储：`config_encrypted` JSONB（dev 环境可读 `.env` ref）

#### Agent 模块

- [ ] ORM `Agent` 模型
- [ ] `GET/POST/PATCH/DELETE /api/v1/agents`
- [ ] `GET /api/v1/agents/roles/templates`（静态角色模板）
- [ ] 校验：agent.provider_id 必须存在

#### Workflow 模板

- [ ] ORM `WorkflowDefinition` + `WorkflowStepDef`
- [ ] `GET/POST /api/v1/workflows/definitions`
- [ ] `GET /api/v1/workflows/definitions/{id}`（含 steps + depends_on）
- [ ] Seed 脚本：写入 `feature-development` 示例工作流（6 步 DAG）

#### 测试

- [ ] pytest：Provider/Agent CRUD 各 1 个集成测试
- [ ] 手动：`/docs` 可创建 Provider + Agent

### 5.3 交付物

- 可 CRUD 的配置 API
- Seed 数据：`openai` Provider + `openai-planner` Agent + `feature-development` 工作流模板

### 5.4 验收标准

- [ ] Postman/curl 创建 Provider 并 list 可见
- [ ] 创建工作流模板含 6 个 step 及 depends_on
- [ ] 前端 Provider / Agent 页可切换为 API（可先只读）

---

## 六、Week 2 — 单 Agent Run + 事件流

### 6.1 目标

不跑完整 DAG，单个 Agent 可发起 Run、流式产生事件、前端 SSE 可见。

### 6.2 任务清单

#### Run 领域

- [ ] ORM `AgentRun`、`AgentEvent`、`AgentMessage`
- [ ] `RunService`：create / get / list / update_status
- [ ] `POST /api/v1/runs`（手动触发单 Agent，body: agent_id + prompt）
- [ ] `GET /api/v1/runs/{id}`
- [ ] `GET /api/v1/runs/{id}/events`
- [ ] `GET /api/v1/runs/{id}/messages`

#### OpenAI Provider（第一个真实 Adapter）

- [ ] `app/providers/openai_provider.py`
- [ ] 实现 `AgentProvider` 协议：`create_session`、`send_task`、`stream_events`
- [ ] 流式 Chat Completions → 映射为 `AgentEvent`：
  - `session_created`
  - `task_started`
  - `assistant_message` / `thinking_update`
  - `agent_completed` / `agent_failed`
- [ ] 写入 `agent_message` 表
- [ ] `test_connection`：调用 models.list 或简单 ping

#### 事件推送

- [ ] `EventPublisher`：事件写 DB 后 publish 到 Redis channel `run:{run_id}`
- [ ] `GET /api/v1/events/stream?run_id=` SSE 实现
- [ ] 支持 `Last-Event-ID` 断线重连（可选 Week 2 末期）

#### 后台任务

- [ ] asyncio 后台 Task：启动 Run 后非阻塞消费 Provider 事件流
- [ ] Run 超时：`limits.timeout_minutes` 自动 cancel

#### 测试

- [ ] 集成测试：创建 Run → 至少收到 3 个 SSE 事件
- [ ] OpenAI Provider unit test（mock httpx）

### 6.3 交付物

- 可通过 API 启动 `openai-planner` 执行一次规划任务
- SSE 客户端（或前端）实时看到 assistant 回复

### 6.4 验收标准

- [ ] `POST /runs` 返回 `run_id`
- [ ] SSE 收到 `assistant_message` 且 DB 有记录
- [ ] Run 结束后 status = `completed`

---

## 七、Week 3 — DAG Orchestrator + Workflow Run

### 7.1 目标

启动完整工作流，按 depends_on 调度，同层 parallel 并发执行。

### 7.2 任务清单

#### Workflow Run 数据

- [ ] ORM `WorkflowRun`、`StepRun`
- [ ] `POST /api/v1/workflows/runs`（启动工作流）
- [ ] `GET /api/v1/workflows/runs`（?status=running）
- [ ] `GET /api/v1/workflows/runs/{id}`（**BPM 核心接口**）

#### OrchestratorService

- [ ] DAG 拓扑排序 + 分层（复用前端同样算法）
- [ ] `start_workflow`：
  1. 创建 WorkflowRun + 全部 StepRun（pending）
  2. 启动无依赖 step
  3. 每 step 创建 AgentRun → 调 Provider
- [ ] `on_step_completed`：检查下游 depends_on 是否满足 → 启动下一批
- [ ] 并行：同层 `parallel=true` 的 step 用 `asyncio.gather`
- [ ] 更新 `workflow_run.progress`
- [ ] 失败策略：step failed → workflow failed（第一期不做自动重试）

#### 多 Provider（模型 API）

- [ ] `AnthropicProvider`（Claude API）
- [ ] `GeminiProvider`（Google API）
- [ ] 注册到 `ProviderRegistry`

#### Step ↔ Run 关联

- [ ] StepRun.agent_run_id 回填
- [ ] AgentEvent 增加 `workflow_run_id`、`step_id` 字段（metadata 或列）

#### SSE 扩展

- [ ] `GET /events/stream?workflow_run_id=` 订阅整工作流事件

#### 测试

- [ ] 集成测试：3 步线性工作流 planning → research → review 顺序执行
- [ ] 集成测试：2 步并行 backend + frontend（mock Provider 快速返回）

### 7.3 交付物

- `POST /workflows/runs` 启动 `feature-development`
- BPM 接口返回 6 步及各自 status / run_id

### 7.4 验收标准

- [ ] planning 完成后自动启动 research
- [ ] research 完成后 backend + frontend 同时 running
- [ ] 全部完成后 workflow status = `completed`

---

## 八、Week 4 — 编程 Agent + 纠正指令 + 监控页联调

### 8.1 目标

Codex / OpenCode 接入，文件变更可见，运行中可 inject 纠正指令，前端运行监控页打通。

### 8.2 任务清单

#### Codex CLI Provider

- [ ] `app/providers/codex_cli.py`
- [ ] subprocess 启动 `codex run`（或项目约定命令）
- [ ] 解析 stdout/stderr → 统一事件：
  - `thinking_update`
  - `tool_call`
  - `file_changed`
  - `command_started` / `command_finished`
- [ ] ORM `FileChange` + `GET /runs/{id}/files`
- [ ] diff 摘要写入 `lines_summary`、`diff` 字段

#### OpenCode CLI Provider

- [ ] `app/providers/opencode_cli.py`
- [ ] 同上模式，适配 opencode 输出格式

#### 纠正指令

- [ ] `POST /api/v1/runs/{id}/messages` body: `{ content, interrupt_current }`
- [ ] `RunService.inject_message`：
  1. 校验 status = running
  2. 写 agent_message（role=user）
  3. 调 Provider.inject_message
  4. 发 `AgentEvent` 通知前端
- [ ] OpenAI/Codex 各自实现 inject（追加 user message 到会话）

#### Run 控制

- [ ] `POST /runs/{id}/pause|resume|cancel`
- [ ] Provider 实现 pause/cancel（CLI 发 signal 或 API cancel）

#### 前端联调（运行监控 + 工作流）

- [ ] 新建 `src/api/client.ts` 封装 fetch
- [ ] `/workflows` 页：拉 `GET /workflows/runs/{id}` 渲染 BPM
- [ ] 点击节点：`GET /runs/{id}/messages|files|events`
- [ ] SSE 订阅替换静态 mock
- [ ] 纠正指令输入框调 `POST /runs/{id}/messages`

#### 测试

- [ ] Codex Provider 集成测试（可用 mock subprocess）
- [ ] inject_message 后 SSE 收到新 user message + assistant 响应

### 8.3 交付物

- 完整「登录功能开发」工作流可跑（Planner OpenAI + Backend Codex + …）
- 前端 BPM + 右侧详情 + 纠正指令端到端

### 8.4 验收标准

- [ ] Codex step 产生 file_changed 事件并在 UI 展示 diff
- [ ] 运行中发送纠正指令，对话区出现新消息
- [ ] 并行 2 条 workflow run 可在监控页切换

---

## 九、Week 5 — 今日计划 + AI 规划 + 全链路

### 9.1 目标

今日计划页接 API，AI 生成详细计划，dev 任务自动触发工作流，step 完成回写计划。

### 9.2 任务清单

#### Schedule 模块

- [ ] ORM `DailyTask`、`TaskPlanItem`
- [ ] `GET /api/v1/schedule/tasks?date=`
- [ ] `POST /api/v1/schedule/tasks`（快速添加）
- [ ] `GET /api/v1/schedule/tasks/{id}`（含 plan_items）
- [ ] `PATCH /api/v1/schedule/tasks/{id}`（更新 status）

#### AI 规划

- [ ] `ScheduleService.plan_today(goal)`：
  1. 调 openai-planner Agent
  2. 解析结构化 JSON → 多条 DailyTask + TaskPlanItem
  3. 写入 DB
- [ ] `POST /api/v1/schedule/tasks/plan-today`
- [ ] `POST /api/v1/schedule/tasks/{id}/regenerate-plan`
- [ ] Prompt 模板：输出 `{ tasks: [{ title, type, plan_items: [...] }] }`

#### 工作流联动

- [ ] dev 类型任务创建时绑定 `workflow_definition_id`
- [ ] `POST /schedule/tasks/{id}/start-workflow` 或 plan_today 时 `auto_start_dev_workflows=true`
- [ ] Orchestrator 完成后回调 `ScheduleService.on_step_completed`：
  - 匹配 `task_plan_item.linked_step_key`
  - 更新 status → done / in_progress

#### 前端联调（今日计划）

- [ ] 左侧清单 `GET /schedule/tasks`
- [ ] 右侧详情 `GET /schedule/tasks/{id}`
- [ ] 快速添加 + AI 规划今日
- [ ] plan_item 上「查看运行」跳 `/runs`

#### Seed + 演示

- [ ] `scripts/seed_demo.py`：一键写入 Provider、Agent、Workflow、今日任务
- [ ] README 演示步骤（5 分钟 demo 脚本）

### 9.3 交付物

- 用户输入「今天完成登录功能」→ 生成计划表 → 自动跑工作流 → 计划步骤状态更新

### 9.4 验收标准

- [ ] 今日计划页无 mock 也可完整演示
- [ ] AI 规划返回 ≥1 条 dev 任务且含 ≥4 个 plan_items
- [ ] 工作流 step 完成 → 对应 plan_item 变 done

---

## 十、Week 6 — 缓冲与收尾

- [ ] Bugfix、边界 case（Provider 断连、CLI 超时、空计划）
- [ ] API 文档与 `docs/api.md` 对齐检查
- [ ] 基础日志（structlog）+ Run 审计字段
- [ ] `.env.example` 完善
- [ ] 可选：GitHub Actions CI（lint + pytest）

---

## 十一、模块与文件对照（后端）

| 模块 | 路径 | 第一期完成周 |
|------|------|-------------|
| 配置 | `app/core/config.py` | W1 |
| ORM | `app/models/*.py` | W1–W3 |
| Provider CRUD | `app/api/v1/providers.py` | W1 |
| Agent CRUD | `app/api/v1/agents.py` | W1 |
| Workflow | `app/api/v1/workflows.py` | W1, W3 |
| Run | `app/api/v1/runs.py` | W2, W4 |
| Schedule | `app/api/v1/schedule.py` | W5 |
| SSE | `app/api/v1/events.py` | W2, W3 |
| OpenAI | `app/providers/openai_provider.py` | W2 |
| Anthropic/Gemini | `app/providers/anthropic_provider.py` 等 | W3 |
| Codex/OpenCode | `app/providers/codex_cli.py` 等 | W4 |
| Orchestrator | `app/services/orchestrator.py` | W3 |
| RunService | `app/services/run_service.py` | W2 |
| ScheduleService | `app/services/schedule_service.py` | W5 |
| EventPublisher | `app/services/event_publisher.py` | W2 |

---

## 十二、第一期 API 交付总表

| 接口 | 周次 | 前端页面 |
|------|------|----------|
| CRUD `/providers` | W1 | Provider 管理 |
| CRUD `/agents` | W1 | Agent 管理 |
| CRUD `/workflows/definitions` | W1 | 工作流配置 |
| `POST/GET /workflows/runs` | W3 | 工作流 BPM |
| `GET /workflows/runs/{id}` | W3 | BPM + 运行监控 |
| `POST/GET /runs` | W2 | 运行监控 |
| `GET /runs/{id}/messages|files|events` | W2/W4 | 节点详情 |
| `POST /runs/{id}/messages` | W4 | 纠正指令 |
| `POST /runs/{id}/pause|cancel` | W4 | 监控页按钮 |
| `GET /events/stream` | W2 | 实时事件 |
| CRUD `/schedule/tasks` | W5 | 今日计划 |
| `POST /schedule/tasks/plan-today` | W5 | AI 规划今日 |

---

## 十三、统一事件类型（第一期必须支持）

```
session_created
task_started
assistant_message
thinking_update
tool_call
command_started
command_finished
file_changed
agent_completed
agent_failed
run_paused
run_cancelled
```

`test_started` / `approval_required` 可在 Phase 2 补全。

---

## 十四、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Codex CLI 输出格式不稳定 | 事件解析失败 | 先做宽松 regex + 原始日志兜底；版本锁定 CLI |
| DAG 自研调度 bug | 步骤卡住 | Week 3 末加 step 超时 watchdog；日志可追踪 |
| SSE 断线 | 前端丢事件 | Redis 缓冲 + Last-Event-ID；前端轮询 events 兜底 |
| OpenAI 流式 API 变更 | Provider 适配 | httpx 封装一层，单测 mock |
| 1 人开发周期紧 | 延期 | Week 6 缓冲；Anthropic/Gemini 可降为「仅 OpenAI」 |

---

## 十五、第一期完成定义（Definition of Done）

以下 **全部满足** 即第一期完成：

1. [ ] Docker Compose 一键启动后端 + DB + Redis
2. [ ] 5 种 Provider kind 至少 **OpenAI + Codex + OpenCode** 真实可跑
3. [ ] `feature-development` 工作流可从启动跑到结束（可 mock 部分 step 加速演示）
4. [ ] 前端 5 个页面（概览除外）**主要数据来自 API**，非 mock
5. [ ] BPM 点击节点 → 对话 / 文件 / 日志 / 纠正指令可用
6. [ ] 今日计划：添加任务 + AI 规划 + 查看详细计划表
7. [ ] dev 任务可触发工作流，step 状态回写 plan_item
8. [ ] README 含 5 分钟演示脚本
9. [ ] 核心路径 pytest ≥ 10 个用例通过

---

## 十六、建议执行顺序（给开发者的一条龙 checklist）

```
□ 1. clone agent-forge，docker compose up
□ 2. Week1：ORM + Provider/Agent/Workflow CRUD + seed
□ 3. Week2：OpenAI Provider + Run + SSE（先打通一条链路）
□ 4. Week3：Orchestrator + WorkflowRun + BPM API
□ 5. Week4：Codex/OpenCode + inject_message + 前端 runs/workflows
□ 6. Week5：Schedule + plan_today + 前端 schedule
□ 7. Week6：demo seed + 文档 + bugfix
□ 8. 演示：plan_today → 工作流跑起来 → BPM 点节点 → 发纠正指令 → 计划回写
```

---

## 十七、相关文档

| 文档 | 路径 |
|------|------|
| 架构设计 | [architecture.md](./architecture.md) |
| 数据库 | [database.md](./database.md) |
| API 规格 | [api.md](./api.md) |
| 总体路线图 | [roadmap.md](./roadmap.md) |
| 前端原型 | `D:\agent-orchestrator-prototype` |

---

*文档维护：随实现进展更新 checkbox 与周次估算。*
