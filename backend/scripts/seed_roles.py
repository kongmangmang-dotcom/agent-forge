"""Create agent_role table and seed builtin roles."""
from __future__ import annotations

import asyncio

import asyncpg

from app.db.session import SessionLocal
from app.models.role import AgentRoleModel
from app.schemas.role import RoleCreate
from app.services.role_service import RoleService

DSN = "postgresql://agentforge:agentforge@localhost:5434/agentforge"

DDL = """
CREATE TABLE IF NOT EXISTS agent_role (
    id                      TEXT PRIMARY KEY,
    code                    TEXT NOT NULL UNIQUE,
    name                    TEXT NOT NULL,
    description             TEXT NOT NULL DEFAULT '',
    system_prompt           TEXT NOT NULL DEFAULT '',
    default_provider_kind   TEXT NOT NULL DEFAULT '',
    sort_order              INTEGER NOT NULL DEFAULT 0,
    is_builtin              BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_role_sort ON agent_role (sort_order, code);
"""

SEED: list[dict] = [
    {
        "code": "planner",
        "name": "Planner",
        "description": "理解需求、拆分任务、建立依赖、制定验收标准",
        "default_provider_kind": "openai",
        "sort_order": 10,
        "system_prompt": (
            "你是规划角色（Planner）。先澄清目标与约束，再拆成可执行任务，"
            "标明依赖与验收标准。输出结构化、简洁，避免直接写业务代码。"
        ),
    },
    {
        "code": "researcher",
        "name": "Researcher",
        "description": "阅读项目结构、分析代码、查找风险",
        "default_provider_kind": "anthropic",
        "sort_order": 20,
        "system_prompt": (
            "你是调研角色（Researcher）。优先阅读仓库结构与关键代码，总结现状、"
            "风险与可选方案，给出有依据的结论，不要擅自大范围改代码。"
        ),
    },
    {
        "code": "developer",
        "name": "Developer",
        "description": "编写代码、修改文件、修复问题",
        "default_provider_kind": "codex_cli",
        "sort_order": 30,
        "system_prompt": (
            "你是开发角色（Developer）。按任务实现功能、修改文件并保证可运行；"
            "改动聚焦目标，补充必要说明，完成后自检关键路径。"
        ),
    },
    {
        "code": "tester",
        "name": "Tester",
        "description": "编写测试、执行测试、分析失败原因",
        "default_provider_kind": "opencode_cli",
        "sort_order": 40,
        "system_prompt": (
            "你是测试角色（Tester）。为改动补充/运行测试，定位失败原因，"
            "给出复现步骤与修复建议；优先保证关键回归覆盖。"
        ),
    },
    {
        "code": "reviewer",
        "name": "Reviewer",
        "description": "检查功能完整性、代码质量、安全问题",
        "default_provider_kind": "gemini",
        "sort_order": 50,
        "system_prompt": (
            "你是评审角色（Reviewer）。从正确性、完整性、可维护性与安全角度审查，"
            "按严重程度列出问题与建议，不直接大改实现除非明确要求。"
        ),
    },
    {
        "code": "integrator",
        "name": "Integrator",
        "description": "合并代码、解决冲突、最终验证",
        "default_provider_kind": "codex_cli",
        "sort_order": 60,
        "system_prompt": (
            "你是集成角色（Integrator）。负责合并变更、解决冲突并做最终联调验证，"
            "确保各模块可一起工作，输出剩余风险清单。"
        ),
    },
    {
        "code": "game_designer",
        "name": "Game Designer",
        "description": "玩法设计、系统设计、数值与关卡、体验节奏",
        "default_provider_kind": "openai",
        "sort_order": 70,
        "system_prompt": (
            "你是游戏设计角色（Game Designer）。聚焦玩法循环、核心机制、系统规则、"
            "数值框架、关卡/内容节奏与玩家体验目标；输出清晰可落地的设计说明"
            "（目标玩家、核心循环、规则表、风险与验收标准）。"
            "除非明确要求，否则不要直接写业务代码或大改工程实现。"
        ),
    },
]


async def ensure_table() -> None:
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute(DDL)
    finally:
        await conn.close()


async def seed() -> None:
    await ensure_table()
    async with SessionLocal() as session:
        svc = RoleService(session)
        existing = {r.code: r for r in await svc.list_roles()}
        created = 0
        updated = 0
        for item in SEED:
            if item["code"] in existing:
                # keep user edits on name/desc/prompt; only ensure builtin flag via re-read
                print("exists", item["code"])
                continue
            await svc.create_role(
                RoleCreate(
                    code=item["code"],
                    name=item["name"],
                    description=item["description"],
                    system_prompt=item["system_prompt"],
                    default_provider_kind=item["default_provider_kind"],
                    sort_order=item["sort_order"],
                ),
                is_builtin=True,
            )
            created += 1
            print("created", item["code"])
        await session.commit()
        print(f"done created={created} updated={updated} total_seed={len(SEED)}")


if __name__ == "__main__":
    asyncio.run(seed())
