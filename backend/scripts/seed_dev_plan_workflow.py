"""Upsert default development-plan workflow — planning only, no coding/review steps."""
from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.ids import new_id
from app.db.session import SessionLocal
from app.models.agent import AgentModel
from app.models.workflow import WorkflowDefinitionModel, WorkflowStepDefModel

WF_NAME = "dev-plan"
WF_TITLE = "标准开发计划"
WF_DESC = "仅生成开发计划：澄清目标 → 拆分任务 → 产出计划与验收标准。不含编码实现与代码评审。"

# planning-only steps
STEP_DEFS = [
    ("clarify", "目标澄清", [], False, "openai-planner"),
    ("breakdown", "任务拆分", ["clarify"], False, "openai-planner"),
    ("plan_output", "计划产出", ["breakdown"], False, "claude-researcher"),
]


async def main() -> None:
    async with SessionLocal() as session:
        agents = (await session.execute(select(AgentModel))).scalars().all()
        by_name = {a.name: a.id for a in agents}
        demo = by_name.get("demo-developer")
        first = agents[0].id if agents else None

        def agent_id(preferred: str) -> str:
            return by_name.get(preferred) or demo or first

        result = await session.execute(
            select(WorkflowDefinitionModel)
            .options(selectinload(WorkflowDefinitionModel.steps))
            .where(WorkflowDefinitionModel.name == WF_NAME)
        )
        row = result.scalar_one_or_none()
        if row:
            row.title = WF_TITLE
            row.description = WF_DESC
            row.options = {
                **(row.options or {}),
                "is_default_dev_plan": True,
                "plan_only": True,
                "reuse_same_agent_session": True,
            }
            row.steps.clear()
            await session.flush()
            wf_id = row.id
            print(f"updating {WF_NAME} {wf_id}")
        else:
            wf_id = "wfd_dev_plan"
            if await session.get(WorkflowDefinitionModel, wf_id):
                wf_id = new_id("wfd")
            row = WorkflowDefinitionModel(
                id=wf_id,
                name=WF_NAME,
                title=WF_TITLE,
                description=WF_DESC,
                options={
                    "is_default_dev_plan": True,
                    "plan_only": True,
                    "reuse_same_agent_session": True,
                },
            )
            session.add(row)
            await session.flush()
            print(f"creating {WF_NAME} {wf_id}")

        for i, (key, label, deps, parallel, agent_name) in enumerate(STEP_DEFS):
            session.add(
                WorkflowStepDefModel(
                    id=new_id("wfs"),
                    workflow_id=wf_id,
                    step_key=key,
                    label=label,
                    agent_id=agent_id(agent_name),
                    depends_on=deps,
                    parallel=parallel,
                    sort_order=i,
                )
            )
        await session.commit()
        print("ok", wf_id, [s[1] for s in STEP_DEFS])


asyncio.run(main())