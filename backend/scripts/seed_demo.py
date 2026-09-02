"""Seed demo data for local development.

Usage (from backend/):
  python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.agent import AgentModel
from app.models.provider import ProviderModel
from app.models.workflow import WorkflowDefinitionModel, WorkflowStepDefModel

PROVIDERS = [
    {
        "id": "prv_openai",
        "kind": "openai",
        "type": "model_api",
        "name": "OpenAI",
        "endpoint": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "config_encrypted": {"api_key_ref": "env:OPENAI_API_KEY"},
        "capabilities": ["规划", "分析", "评审", "问答"],
        "status": "disconnected",
    },
    {
        "id": "prv_anthropic",
        "kind": "anthropic",
        "type": "model_api",
        "name": "Anthropic",
        "endpoint": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4",
        "config_encrypted": {"api_key_ref": "env:ANTHROPIC_API_KEY"},
        "capabilities": ["调研", "代码分析", "长文本"],
        "status": "disconnected",
    },
    {
        "id": "prv_gemini",
        "kind": "gemini",
        "type": "model_api",
        "name": "Gemini",
        "endpoint": "https://generativelanguage.googleapis.com",
        "default_model": "gemini-2.5-pro",
        "config_encrypted": {"api_key_ref": "env:GEMINI_API_KEY"},
        "capabilities": ["评审", "多模态", "技术分析"],
        "status": "disconnected",
    },
    {
        "id": "prv_codex",
        "kind": "codex_cli",
        "type": "coding_agent",
        "name": "Codex CLI",
        "endpoint": "codex run",
        "default_model": "default",
        "config_encrypted": {
            "cli_command": r"C:\nvm4w\nodejs\codex.cmd",
            "cli_args": ["exec", "--full-auto"],
            "api_key_ref": "env:OPENAI_API_KEY",
        },
        "capabilities": ["读写代码", "执行命令", "Git Diff"],
        "status": "disconnected",
    },
    {
        "id": "prv_opencode",
        "kind": "opencode_cli",
        "type": "coding_agent",
        "name": "OpenCode CLI",
        "endpoint": "opencode run",
        "default_model": "default",
        "config_encrypted": {"cli_command": "opencode"},
        "capabilities": ["测试编写", "命令执行"],
        "status": "disconnected",
    },
    {
        "id": "prv_demo",
        "kind": "demo_cli",
        "type": "coding_agent",
        "name": "Demo CLI（本地测试）",
        "endpoint": "python demo_agent_runner",
        "default_model": "default",
        "config_encrypted": {},
        "capabilities": ["本地演示", "无需安装 Codex"],
        "status": "connected",
    },
    {
        "id": "prv_cursor",
        "kind": "cursor_cli",
        "type": "coding_agent",
        "name": "Cursor Agent",
        "endpoint": "cursor agent",
        "default_model": "composer",
        "config_encrypted": {"cli_command": "cursor", "cli_args": ["agent"]},
        "capabilities": ["前端开发", "IDE Agent"],
        "status": "disconnected",
    },
]

AGENTS = [
    {
        "id": "agt_openai_planner",
        "name": "openai-planner",
        "provider_id": "prv_openai",
        "model": "gpt-4o",
        "role": "planner",
        "workspace_path": "",
        "permissions": {
            "read_files": True,
            "write_files": False,
            "run_commands": False,
            "run_tests": False,
            "network": False,
        },
        "limits": {"timeout_minutes": 15, "max_rounds": 2},
    },
    {
        "id": "agt_claude_researcher",
        "name": "claude-researcher",
        "provider_id": "prv_anthropic",
        "model": "claude-sonnet-4",
        "role": "researcher",
        "workspace_path": "project-a",
        "permissions": {
            "read_files": True,
            "write_files": False,
            "run_commands": False,
            "run_tests": False,
            "network": True,
        },
        "limits": {"timeout_minutes": 20, "max_rounds": 3},
    },
    {
        "id": "agt_codex_backend",
        "name": "codex-backend",
        "provider_id": "prv_codex",
        "model": "default",
        "role": "developer",
        "workspace_path": "D:/solarsense-backend",
        "permissions": {
            "read_files": True,
            "write_files": True,
            "run_commands": True,
            "run_tests": True,
            "network": False,
        },
        "limits": {"timeout_minutes": 30, "max_rounds": 5},
    },
    {
        "id": "agt_opencode_tester",
        "name": "opencode-tester",
        "provider_id": "prv_opencode",
        "model": "default",
        "role": "tester",
        "workspace_path": "project-a",
        "permissions": {
            "read_files": True,
            "write_files": True,
            "run_commands": True,
            "run_tests": True,
            "network": False,
        },
        "limits": {"timeout_minutes": 20, "max_rounds": 3},
    },
    {
        "id": "agt_gemini_reviewer",
        "name": "gemini-reviewer",
        "provider_id": "prv_gemini",
        "model": "gemini-2.5-pro",
        "role": "reviewer",
        "workspace_path": "",
        "permissions": {
            "read_files": True,
            "write_files": False,
            "run_commands": False,
            "run_tests": False,
            "network": False,
        },
        "limits": {"timeout_minutes": 15, "max_rounds": 2},
        "streaming": False,
    },
    {
        "id": "agt_demo_dev",
        "name": "demo-developer",
        "provider_id": "prv_demo",
        "model": "default",
        "role": "developer",
        "workspace_path": "workspace/demo",
        "permissions": {
            "read_files": True,
            "write_files": True,
            "run_commands": True,
            "run_tests": True,
            "network": False,
        },
        "limits": {"timeout_minutes": 30, "max_rounds": 5},
    },
]

WORKFLOW = {
    "id": "wfd_dev_plan",
    "name": "dev-plan",
    "title": "标准开发计划",
    "description": "仅生成开发计划：澄清目标 → 拆分任务 → 产出计划与验收标准。不含编码实现与代码评审。",
    "steps": [
        {
            "id": "wfs_dev_clarify",
            "step_key": "clarify",
            "label": "目标澄清",
            "agent_id": "agt_openai_planner",
            "depends_on": [],
            "parallel": False,
            "sort_order": 0,
        },
        {
            "id": "wfs_dev_breakdown",
            "step_key": "breakdown",
            "label": "任务拆分",
            "agent_id": "agt_openai_planner",
            "depends_on": ["clarify"],
            "parallel": False,
            "sort_order": 1,
        },
        {
            "id": "wfs_dev_plan_output",
            "step_key": "plan_output",
            "label": "计划产出",
            "agent_id": "agt_claude_researcher",
            "depends_on": ["breakdown"],
            "parallel": False,
            "sort_order": 2,
        },
    ],
}


async def seed() -> None:
    async with SessionLocal() as session:
        existing = await session.execute(select(ProviderModel.id).limit(1))
        if existing.scalar_one_or_none():
            print("Seed skipped: data already exists")
            return

        for p in PROVIDERS:
            session.add(ProviderModel(**p))
        for a in AGENTS:
            session.add(AgentModel(**a))
        wf = WorkflowDefinitionModel(
            id=WORKFLOW["id"],
            name=WORKFLOW["name"],
            title=WORKFLOW["title"],
            description=WORKFLOW["description"],
            options={
                "is_default_dev_plan": True,
                "plan_only": True,
                "reuse_same_agent_session": True,
                "tags": ["计划"],
            },
        )
        session.add(wf)
        await session.flush()
        for step in WORKFLOW["steps"]:
            session.add(WorkflowStepDefModel(workflow_id=WORKFLOW["id"], **step))
        await session.commit()
        print(
            f"Seeded {len(PROVIDERS)} providers, {len(AGENTS)} agents, "
            f"1 workflow ({len(WORKFLOW['steps'])} steps)"
        )


if __name__ == "__main__":
    asyncio.run(seed())
