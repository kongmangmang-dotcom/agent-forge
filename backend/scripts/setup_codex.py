"""Configure local Codex CLI provider and agent for AgentForge."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.agent import AgentModel
from app.models.provider import ProviderModel

CODEX_CMD = Path(r"C:\nvm4w\nodejs\codex.cmd")
CODEX_EXE = Path(
    r"C:\Users\Administrator\AppData\Local\nvm\v22.21.1\node_modules"
    r"\@openai\codex\node_modules\@openai\codex-win32-x64"
    r"\vendor\x86_64-pc-windows-msvc\bin\codex.exe"
)
WORKSPACE = Path(r"D:\solarsense-backend")


def resolve_codex_command() -> str:
    if CODEX_CMD.is_file():
        return str(CODEX_CMD)
    found = shutil.which("codex")
    if found:
        return found
    if CODEX_EXE.is_file():
        return str(CODEX_EXE)
    raise SystemExit("Codex CLI not found. Run: npm install -g @openai/codex")


async def main() -> None:
    cli_command = resolve_codex_command()
    print(f"Using Codex CLI: {cli_command}")

    async with SessionLocal() as db:
        provider = await db.get(ProviderModel, "prv_codex")
        if not provider:
            raise SystemExit("Provider prv_codex not found. Run seed_demo.py first.")

        provider.config_encrypted = {
            "cli_command": cli_command,
            "cli_args": ["exec", "--full-auto"],
            "api_key_ref": "env:OPENAI_API_KEY",
        }
        provider.endpoint = "codex exec"
        provider.status = "connected"

        result = await db.execute(select(AgentModel).where(AgentModel.id == "agt_codex_backend"))
        agent = result.scalar_one_or_none()
        if agent:
            agent.workspace_path = str(WORKSPACE).replace("\\", "/")

        await db.commit()
        print("Updated prv_codex provider config")
        if agent:
            print(f"Updated agt_codex_backend workspace -> {agent.workspace_path}")
        print("Done. Test at: POST /api/v1/providers/prv_codex/test")


if __name__ == "__main__":
    asyncio.run(main())
