from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.ids import new_id
from app.models.agent import AgentModel
from app.models.provider import ProviderModel
from app.schemas.agent import AgentCreate, AgentRead, AgentUpdate


def _to_read(row: AgentModel) -> AgentRead:
    provider_name = row.provider.name if row.provider else None
    return AgentRead(
        id=row.id,
        name=row.name,
        provider_id=row.provider_id,
        provider_name=provider_name,
        model=row.model,
        role=row.role,
        system_prompt=row.system_prompt,
        workspace_path=row.workspace_path,
        permissions=row.permissions or {},
        limits=row.limits or {},
        streaming=row.streaming,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AgentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _ensure_provider(self, provider_id: str) -> None:
        if not await self.db.get(ProviderModel, provider_id):
            raise ValidationError(f"provider_id does not exist: {provider_id}")

    async def list_agents(self) -> list[AgentRead]:
        result = await self.db.execute(
            select(AgentModel)
            .options(joinedload(AgentModel.provider))
            .order_by(AgentModel.name)
        )
        return [_to_read(r) for r in result.scalars().unique().all()]

    async def get_agent(self, agent_id: str) -> AgentRead:
        row = await self._get_agent_row(agent_id)
        return _to_read(row)

    async def _get_agent_row(self, agent_id: str) -> AgentModel:
        result = await self.db.execute(
            select(AgentModel)
            .options(joinedload(AgentModel.provider))
            .where(AgentModel.id == agent_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise NotFoundError("Agent", agent_id)
        return row

    async def create_agent(self, data: AgentCreate) -> AgentRead:
        await self._ensure_provider(data.provider_id)
        row = AgentModel(
            id=new_id("agt"),
            name=data.name,
            provider_id=data.provider_id,
            model=data.model,
            role=data.role,
            system_prompt=data.system_prompt,
            workspace_path=data.workspace_path,
            permissions=data.permissions.model_dump(),
            limits=data.limits.model_dump(),
            streaming=data.streaming,
        )
        self.db.add(row)
        await self.db.flush()
        row = await self._get_agent_row(row.id)
        return _to_read(row)

    async def update_agent(self, agent_id: str, data: AgentUpdate) -> AgentRead:
        row = await self._get_agent_row(agent_id)
        updates = data.model_dump(exclude_unset=True)
        if "provider_id" in updates:
            await self._ensure_provider(updates["provider_id"])
        if data.permissions is not None:
            row.permissions = data.permissions.model_dump()
            updates.pop("permissions", None)
        if data.limits is not None:
            row.limits = data.limits.model_dump()
            updates.pop("limits", None)
        for key, value in updates.items():
            setattr(row, key, value)
        await self.db.flush()
        row = await self._get_agent_row(agent_id)
        return _to_read(row)

    async def delete_agent(self, agent_id: str) -> None:
        row = await self.db.get(AgentModel, agent_id)
        if not row:
            raise NotFoundError("Agent", agent_id)
        name = row.name
        await self.db.delete(row)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "AGENT_IN_USE",
                f"无法删除 Agent「{name}」：仍被工作流步骤引用，请先从工作流中移除",
            ) from exc
