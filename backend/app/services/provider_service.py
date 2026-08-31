from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.ids import new_id
from app.models.provider import ProviderModel
from app.schemas.provider import ProviderCreate, ProviderRead, ProviderUpdate


def _to_read(row: ProviderModel) -> ProviderRead:
    return ProviderRead(
        id=row.id,
        kind=row.kind,
        type=row.type,
        name=row.name,
        endpoint=row.endpoint,
        default_model=row.default_model,
        config=row.config_encrypted,
        capabilities=row.capabilities or [],
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ProviderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_providers(self) -> list[ProviderRead]:
        result = await self.db.execute(select(ProviderModel).order_by(ProviderModel.name))
        return [_to_read(r) for r in result.scalars().all()]

    async def get_provider(self, provider_id: str) -> ProviderRead:
        row = await self.db.get(ProviderModel, provider_id)
        if not row:
            raise NotFoundError("Provider", provider_id)
        return _to_read(row)

    async def create_provider(self, data: ProviderCreate) -> ProviderRead:
        row = ProviderModel(
            id=new_id("prv"),
            kind=data.kind,
            type=data.type.value,
            name=data.name,
            endpoint=data.endpoint,
            default_model=data.default_model,
            config_encrypted=data.config,
            capabilities=data.capabilities,
            status="disconnected",
        )
        self.db.add(row)
        await self.db.flush()
        return _to_read(row)

    async def update_provider(self, provider_id: str, data: ProviderUpdate) -> ProviderRead:
        row = await self.db.get(ProviderModel, provider_id)
        if not row:
            raise NotFoundError("Provider", provider_id)
        updates = data.model_dump(exclude_unset=True)
        if "config" in updates:
            row.config_encrypted = updates.pop("config")
        if "type" in updates and updates["type"] is not None:
            row.type = updates["type"].value
            del updates["type"]
        for key, value in updates.items():
            setattr(row, key, value)
        await self.db.flush()
        return _to_read(row)

    async def delete_provider(self, provider_id: str) -> None:
        row = await self.db.get(ProviderModel, provider_id)
        if not row:
            raise NotFoundError("Provider", provider_id)
        await self.db.delete(row)

    async def test_connection(self, provider_id: str) -> tuple[bool, str, int | None]:
        row = await self.db.get(ProviderModel, provider_id)
        if not row:
            raise NotFoundError("Provider", provider_id)
        # Week 2: real provider adapter test; Week 1 returns config check only
        if row.kind in ("openai", "anthropic", "gemini"):
            key_ref = (row.config_encrypted or {}).get("api_key_ref", "")
            if key_ref.startswith("env:"):
                import os

                env_key = key_ref.split(":", 1)[1]
                if os.getenv(env_key):
                    row.status = "connected"
                    return True, f"API key configured via {key_ref}", None
                row.status = "disconnected"
                return False, f"Missing environment variable: {env_key}", None
            return False, "Set config.api_key_ref to env:OPENAI_API_KEY (etc.)", None
        if row.kind in ("codex_cli", "opencode_cli", "cursor_cli"):
            cmd = (row.config_encrypted or {}).get("cli_command", row.kind.replace("_cli", ""))
            import shutil
            from pathlib import Path

            cmd_path = Path(str(cmd))
            if cmd_path.is_file() or shutil.which(str(cmd)) or cmd == "cursor":
                row.status = "connected"
                resolved = str(cmd_path) if cmd_path.is_file() else (shutil.which(str(cmd)) or cmd)
                return True, f"CLI command configured: {resolved}", None
            row.status = "disconnected"
            return False, f"CLI not found in PATH: {cmd}. Use demo_cli to test without install.", None
        if row.kind == "demo_cli":
            row.status = "connected"
            return True, "Demo CLI ready (built-in Python runner)", None
        row.status = "disconnected"
        return False, f"Unknown provider kind: {row.kind}", None
