# AgentForge

独立 Agent 编排平台 — 多 Provider、工作流 BPM、今日计划、运行中纠正指令。

## 仓库结构

```
agent-forge/
├── docs/                 # 设计文档
├── backend/              # FastAPI 主服务
├── web/                  # 前端（可 symlink 或迁移 agent-orchestrator-prototype）
└── docker-compose.yml    # PostgreSQL + Redis + API
```

## 快速开始（Week 1 已实现）

### 1. 启动数据库

```bash
# 项目根目录 — Postgres :5434, Redis :6380（避免与现有 5433/6379 冲突）
docker compose up -d postgres redis
```

### 2. 启动 API

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
copy .env.example .env
python -m scripts.seed_demo
uvicorn app.main:app --reload --port 8001
```

> **Windows 注意事项**：CLI Provider（Codex/Cursor/OpenCode）依赖 `asyncio` 子进程，
> 而 uvicorn 在 Windows 上只要带 `--reload` 就会使用 SelectorEventLoop（不支持子进程），
> 导致所有 CLI run 秒失败（`NotImplementedError`，事件内容为空）。
> 请务必**不带 `--reload` 启动**：`uvicorn app.main:app --port 8001`，改代码后手动重启。

- API 文档：http://localhost:8001/docs
- 健康检查：http://localhost:8001/health

### Week 1 已交付 API

| 模块 | 接口 |
|------|------|
| Provider | `GET/POST/PATCH/DELETE /api/v1/providers`, `POST .../test` |
| Agent | `GET/POST/PATCH/DELETE /api/v1/agents`, `GET .../roles/templates` |
| Workflow 模板 | `GET/POST /api/v1/workflows/definitions`, `GET/DELETE .../{id}` |

Run / Orchestrator / Schedule 仍为 Week 2+ 占位。

**开发约定**：每实现一组后端 API，须同步在前端 `agent-orchestrator-prototype` 接入（`src/api/` + 页面调用），不得只写后端留 mock。

## 设计文档

| 文档 | 内容 |
|------|------|
| [docs/phase-1-plan.md](docs/phase-1-plan.md) | **第一期完整实现计划（5–6 周）** |
| [docs/architecture.md](docs/architecture.md) | 架构、模块边界、Provider 协议 |
| [docs/database.md](docs/database.md) | 表结构、索引、状态机 |
| [docs/api.md](docs/api.md) | REST + SSE API（对齐前端原型） |

## 技术栈

- **Python 3.12** + FastAPI + Pydantic v2
- **PostgreSQL** 持久化
- **Redis** Run 状态、事件缓冲、任务队列
- **SSE** 实时事件推送

## 第一版 Provider

- OpenAI / Anthropic / Gemini（HTTP API）
- Codex CLI / OpenCode CLI（subprocess Adapter）
