import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.ids import new_id
from app.models.role import AgentRoleModel
from app.schemas.role import RoleCreate, RoleRead, RoleUpdate

_CODE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def _to_read(row: AgentRoleModel) -> RoleRead:
    return RoleRead(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description or "",
        system_prompt=row.system_prompt or "",
        default_provider_kind=row.default_provider_kind or "",
        sort_order=row.sort_order,
        is_builtin=bool(row.is_builtin),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _normalize_code(code: str) -> str:
    value = (code or "").strip().lower().replace(" ", "-")
    if not _CODE_RE.match(value):
        raise ValidationError(
            "角色 code 需为小写字母开头，仅含 a-z / 0-9 / _ / -（如 planner、docs-writer）"
        )
    return value


class RoleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_roles(self) -> list[RoleRead]:
        result = await self.db.execute(
            select(AgentRoleModel).order_by(AgentRoleModel.sort_order, AgentRoleModel.code)
        )
        return [_to_read(r) for r in result.scalars().all()]

    async def get_role(self, role_id: str) -> RoleRead:
        row = await self.db.get(AgentRoleModel, role_id)
        if not row:
            raise NotFoundError("Role", role_id)
        return _to_read(row)

    async def get_by_code(self, code: str) -> RoleRead | None:
        normalized = (code or "").strip().lower()
        if not normalized:
            return None
        result = await self.db.execute(
            select(AgentRoleModel).where(AgentRoleModel.code == normalized)
        )
        row = result.scalar_one_or_none()
        return _to_read(row) if row else None

    async def create_role(self, data: RoleCreate, *, is_builtin: bool = False) -> RoleRead:
        code = _normalize_code(data.code)
        row = AgentRoleModel(
            id=new_id("rol"),
            code=code,
            name=data.name.strip(),
            description=(data.description or "").strip(),
            system_prompt=(data.system_prompt or "").strip(),
            default_provider_kind=(data.default_provider_kind or "").strip(),
            sort_order=data.sort_order,
            is_builtin=is_builtin,
        )
        self.db.add(row)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ConflictError("ROLE_CODE_EXISTS", f"角色 code 已存在: {code}") from exc
        await self.db.refresh(row)
        return _to_read(row)

    async def update_role(self, role_id: str, data: RoleUpdate) -> RoleRead:
        row = await self.db.get(AgentRoleModel, role_id)
        if not row:
            raise NotFoundError("Role", role_id)
        updates = data.model_dump(exclude_unset=True)
        if "code" in updates and updates["code"] is not None:
            updates["code"] = _normalize_code(updates["code"])
        for key in ("name", "description", "system_prompt", "default_provider_kind"):
            if key in updates and updates[key] is not None:
                updates[key] = str(updates[key]).strip()
        for key, value in updates.items():
            setattr(row, key, value)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "ROLE_CODE_EXISTS",
                f"角色 code 已存在: {row.code}",
            ) from exc
        await self.db.refresh(row)
        return _to_read(row)

    async def delete_role(self, role_id: str) -> None:
        row = await self.db.get(AgentRoleModel, role_id)
        if not row:
            raise NotFoundError("Role", role_id)
        if row.is_builtin:
            raise ConflictError("ROLE_BUILTIN", f"内置角色「{row.name}」不可删除，可编辑描述与提示词")
        await self.db.delete(row)
        await self.db.flush()
