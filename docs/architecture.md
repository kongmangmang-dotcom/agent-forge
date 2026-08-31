# AgentForge 架构设计

## 1. 设计原则

1. **Orchestrator 居中**：Agent 不直接互调，所有跨 Agent 行为经编排器
2. **Provider 可插拔**：核心只认 `AgentProvider` 接口，不依赖 Codex/OpenAI 实现
3. **事件驱动**：前端、审计、计划回写均消费统一 `AgentEvent`
4. **平台自持会话**：Run / Message / FileChange 自存储，不读外部工具历史
5. **运行中可干预**：`inject_message` 经 Orchestrator 转发 Provider

## 2. 逻辑分层

```
┌─────────────────────────────────────────────────────────────┐
│  Web (React) — 原型页：Provider / Agent / Workflow / Runs / Schedule │
└────────────────────────────┬────────────────────────────────┘
                             │ REST + SSE
┌────────────────────────────▼────────────────────────────────┐
│  API Layer (FastAPI)                                         │
│  /providers /agents /workflows /runs /schedule /events/sse   │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│  Application Services                                        │
│  OrchestratorService · RunService · ScheduleService           │
│  WorkflowService · ProviderRegistry · EventPublisher          │
└──────────────┬─────────────────────────────┬────────────────┘
               │                             │
┌──────────────▼──────────────┐   ┌──────────▼──────────────────┐
│  PostgreSQL                  │   │  Redis                     │
│  配置 / 计划 / Run 持久化     │   │  Run 状态 / 事件流 / 队列   │
└──────────────────────────────┘   └────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│  Provider Adapter Layer                                      │
│  OpenAI · Anthropic · Gemini · CodexCLI · OpenCodeCLI · …    │
└──────────────────────────────────────────────────────────────┘
```

## 3. 核心领域模型

| 实体 | 说明 |
|------|------|
| `Provider` | 接入配置（类型、endpoint、密钥引用） |
| `Agent` | 角色 + Provider + 权限 + 工作区 |
| `WorkflowDefinition` | 工作流模板（DAG steps + depends_on） |
| `WorkflowRun` | 一次工作流执行实例 |
| `StepRun` | 工作流中单步执行，1:1 对应 Agent Run |
| `AgentRun` | 单次 Agent 会话执行（run_id） |
| `AgentEvent` | 统一事件（tool_call、file_changed…） |
| `DailyTask` | 今日计划条目 |
| `TaskPlanItem` | AI 生成的详细计划步骤 |

## 4. AgentProvider 协议

所有 Provider 实现同一接口（Python Protocol）：

```python
class AgentProvider(Protocol):
    provider_type: ProviderType  # model_api | coding_agent | local_runtime

    async def test_connection(self, config: ProviderConfig) -> ConnectionResult: ...

    async def create_session(self, agent: AgentConfig, workspace: Workspace) -> SessionHandle: ...

    async def send_task(self, session: SessionHandle, task: TaskPayload) -> None: ...

    async def inject_message(self, session: SessionHandle, message: str) -> None:
        """运行中用户纠正指令"""

    async def stream_events(self, session: SessionHandle) -> AsyncIterator[AgentEvent]: ...

    async def pause / resume / cancel(self, session: SessionHandle) -> None: ...

    async def get_file_changes(self, session: SessionHandle) -> list[FileChange]: ...
```

**注册方式**：`ProviderRegistry` 按 `provider.kind` 解析实现类，配置存 DB。

## 5. Orchestrator 工作流引擎

### 5.1 DAG 调度

- 输入：`WorkflowDefinition.steps[]` + `depends_on[]`
- 拓扑排序分层；同层 `parallel=true` 的步骤并发执行
- 状态：`pending → running → completed | failed | waiting_approval`

### 5.2 执行循环（单 Step）

```
1. 解析 Agent 配置 + 权限校验
2. Provider.create_session
3. Provider.send_task(prompt + 上下文)
4. 消费 stream_events → 写 DB + 推 SSE
5. 若收到 inject_message → Provider.inject_message
6. 完成 / 失败 → 更新 StepRun，触发下游 depends_on 满足检查
7. 全部完成 → WorkflowRun.completed，回写 DailyTask（若关联）
```

### 5.3 边界

- Agent **不能**直接调用另一个 Agent
- 纠正指令 **必须** `POST /runs/{id}/messages` → Orchestrator → Provider
- 人工审批：`waiting_approval` 暂停 DAG，直到 `POST /runs/{id}/approve`

## 6. 事件系统

### 6.1 统一事件格式

```json
{
  "run_id": "run_xxx",
  "agent_id": "codex-backend",
  "workflow_run_id": "wfr_xxx",
  "step_id": "backend",
  "type": "file_changed",
  "status": "completed",
  "content": "修改 AuthController.java",
  "metadata": { "path": "src/...", "action": "modified" },
  "timestamp": "2026-08-27T10:00:00Z"
}
```

### 6.2 推送

- **SSE** `GET /events/stream?run_id=` — 单 Run 订阅
- **SSE** `GET /events/stream?workflow_run_id=` — 整工作流订阅
- Redis Pub/Sub 作 API 多实例广播（后期）

## 7. 今日计划联动

```
POST /schedule/tasks          用户添加 / AI 规划
    → ScheduleService
    → PlannerProvider (OpenAI) 生成 plan_items
    → 若 type=dev → WorkflowService.start(workflow_definition_id)
    
StepRun / AgentRun 状态变更
    → EventHandler 回写 task_plan_item.status
    → 可选：Planner 重新生成 POST /schedule/tasks/{id}/regenerate-plan
```

## 8. 目录结构（backend）

```
backend/app/
├── main.py                 # FastAPI 入口
├── core/                   # 配置、依赖、异常
├── domain/                 # 枚举、Protocol、纯领域类型
├── models/                 # SQLAlchemy ORM
├── schemas/                # Pydantic 请求/响应
├── api/v1/                 # 路由
│   ├── providers.py
│   ├── agents.py
│   ├── workflows.py
│   ├── runs.py
│   ├── schedule.py
│   └── events.py           # SSE
├── services/
│   ├── orchestrator.py
│   ├── run_service.py
│   ├── workflow_service.py
│   ├── schedule_service.py
│   └── event_publisher.py
└── providers/
    ├── base.py
    ├── registry.py
    ├── openai_provider.py
    ├── anthropic_provider.py
    ├── codex_cli.py
    └── opencode_cli.py
```

## 9. 演进路线

| 阶段 | 内容 |
|------|------|
| **M1** | Provider/Agent/Workflow CRUD + 单 Agent Run + SSE |
| **M2** | DAG Orchestrator + 并行 + inject_message |
| **M3** | Schedule + AI 计划 + 工作流联动 |
| **M4** | 审批节点、重试策略、Temporal 可选替换自研调度 |

## 10. 非目标（第一版）

- 多租户 / SSO（预留 `workspace_id`）
- Cursor/Hermes 专用 Adapter（通用 CLI Adapter 后续扩展）
- 与 SolarSense 集成
