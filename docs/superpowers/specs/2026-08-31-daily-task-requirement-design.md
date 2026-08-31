# Daily Task: title + requirement

**Date:** 2026-08-31  
**Status:** approved / implemented  
**Repos:** agent-forge backend + agent-orchestrator-prototype Schedule UI

## Goal

用户只输入**详细需求** → 系统生成**短标题** + **开发计划表**。生成之后，详情页必须仍能看到并**重新配置该需求**（以及标题），保存后可再用来启动工作流 / 刷新计划。

## Product flow

```
[用户输入 requirement]
        ↓
[系统派生 title（短标题）]
        ↓
[按绑定工作流模板生成 plan_items]
        ↓
[详情页：可编辑 title + requirement → 保存]
        ↓
[启动工作流时 prompt 优先用 requirement]
```

详情页布局（相对现状截图）：在「配置本任务的开发工作流」**之上**增加「任务要求」卡片：

1. 短标题（可改）
2. 详细需求（可改，多行）
3. 保存按钮  
其下保持：工作流配置 → 状态/来源 → 开发计划表

## Data model

| Field | Role |
|-------|------|
| `requirement` | 用户输入的详细需求（权威）；刷新计划**不得**覆盖 |
| `title` | 短标题；创建时由 requirement 派生，之后可手改 |
| `summary` | 系统短摘要（如「开发计划（标准开发计划）」）；不覆盖 requirement |

Migration: `003_daily_task_requirement.sql`  
`ALTER TABLE daily_task ADD COLUMN IF NOT EXISTS requirement TEXT NOT NULL DEFAULT '';`  
Backfill: empty `requirement` ← copy from non-empty `summary` when useful.

## Create UX

**生成开发计划**
- 主输入：详细需求 textarea（必填）
- 不要求用户另填标题；后端用 requirement 首行/截断（约 80 字）生成 `title`
- `requirement` = 原文；`summary` = 系统摘要

**快速添加**
- 标题必填；requirement 可选（详情里补）

## API / backend

- Schemas + model + PATCH 支持 `requirement`
- `plan_today(goal)`：`requirement=goal`，`title=derive(goal)`，`summary=系统摘要`，再生成 plan
- `_replace_plan_items`：禁止写 `requirement`；`summary` 仅空时补系统摘要
- `start_task_workflow` prompt：显式 `task_prompt` → `requirement` → `summary` → `title`

## Note on “AI 生成计划”

当前计划表步骤来自**工作流模板 DAG**（非 LLM 现场编步骤）。本设计不改变该机制；若以后要 LLM 改写步骤内容，另开需求。标题 v1 为规则派生，不做单独 LLM 调用来起标题。

## Out of scope

- 编辑单条 plan_item
- 从详情改 DAG 结构
- LLM 自动起标题 / 自动改写步骤正文

## Acceptance

1. 用需求生成任务后，详情顶部能看到完整 requirement，可改并保存。
2. 刷新/重新应用工作流不丢失 requirement。
3. 启动工作流使用已保存的 requirement。
4. 旧任务无 requirement 时仍可打开；编辑器可预填 summary/title，点保存后写入 requirement。
