"""Upsert demo_cli provider + agent on existing DB."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.agent import AgentModel
from app.models.provider import ProviderModel

DEMO_PROVIDER = {
    "id": "prv_demo",
    "kind": "demo_cli",
    "type": "coding_agent",
    "name": "Demo CLI（本地测试）",
    "endpoint": "python demo_agent_runner",
    "default_model": "default",
    "config_encrypted": {},
    "capabilities": ["本地演示", "无需安装 Codex"],
    "status": "connected",
}

DEMO_AGENT = {
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
}


async def main() -> None:
    async with SessionLocal() as session:
        if not await session.get(ProviderModel, "prv_demo"):
            session.add(ProviderModel(**DEMO_PROVIDER))
            print("Added prv_demo")
        if not await session.get(AgentModel, "agt_demo_dev"):
            session.add(AgentModel(**DEMO_AGENT))
            print("Added agt_demo_dev")
        await session.commit()
        print("Done")


if __name__ == "__main__":
    asyncio.run(main())
