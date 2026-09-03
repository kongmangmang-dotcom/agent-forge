from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.ids import new_id
from app.models.agent import AgentModel
from app.models.workflow import WorkflowDefinitionModel, WorkflowStepDefModel
from app.schemas.workflow import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionRead,
    WorkflowDefinitionSummary,
    WorkflowDefinitionUpdate,
    WorkflowStepDefRead,
)

# 预设分类标签（创建页可点选；也可自定义）
WELL_KNOWN_WORKFLOW_TAGS = ("计划", "开发")


def _normalize_tags(raw: list | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in raw or []:
        tag = str(item).strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def _tags_from_options(options: dict | None) -> list[str]:
    if not isinstance(options, dict):
        return []
    raw = options.get("tags")
    return _normalize_tags(raw if isinstance(raw, list) else None)


def _options_with_tags(
    options: dict | None,
    tags: list[str] | None,
    *,
    tags_provided: bool,
) -> dict:
    merged = dict(options or {})
    if tags_provided:
        merged["tags"] = _normalize_tags(tags)
    elif "tags" in merged:
        merged["tags"] = _tags_from_options(merged)
    return merged


def _normalize_on_complete(value: str | None) -> str:
    v = (value or "none").strip().lower()
    if v in ("none", "notify", "confirm"):
        return v
    return "none"


def _step_read(step: WorkflowStepDefModel, agent_names: dict[str, str]) -> WorkflowStepDefRead:
    return WorkflowStepDefRead(
        id=step.id,
        step_key=step.step_key,
        label=step.label,
        agent_id=step.agent_id,
        agent_name=agent_names.get(step.agent_id),
        role=(step.role or "").strip(),
        depends_on=step.depends_on or [],
        parallel=step.parallel,
        on_complete=_normalize_on_complete(getattr(step, "on_complete", None)),
        sort_order=step.sort_order,
    )


def _definition_read(
    row: WorkflowDefinitionModel, agent_names: dict[str, str]
) -> WorkflowDefinitionRead:
    options = row.options or {}
    return WorkflowDefinitionRead(
        id=row.id,
        name=row.name,
        title=row.title,
        description=row.description,
        tags=_tags_from_options(options),
        options=options,
        created_at=row.created_at,
        steps=[_step_read(s, agent_names) for s in row.steps],
    )


def _validate_dag_acyclic(step_keys: set[str], depends_map: dict[str, list[str]]) -> None:
    if not step_keys:
        return
    in_degree = {key: 0 for key in step_keys}
    for key in step_keys:
        for dep in depends_map.get(key, []):
            if dep in step_keys:
                in_degree[key] += 1
    queue = [key for key, degree in in_degree.items() if degree == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for other in step_keys:
            if node in depends_map.get(other, []):
                in_degree[other] -= 1
                if in_degree[other] == 0:
                    queue.append(other)
    if visited != len(step_keys):
        raise ValidationError("DAG contains a cycle")


class WorkflowService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _agent_names(self, agent_ids: set[str]) -> dict[str, str]:
        if not agent_ids:
            return {}
        result = await self.db.execute(
            select(AgentModel.id, AgentModel.name).where(AgentModel.id.in_(agent_ids))
        )
        return dict(result.all())

    async def _validate_steps(self, steps: list) -> None:
        keys = {s.step_key for s in steps}
        if len(keys) != len(steps):
            raise ValidationError("step_key must be unique within workflow")
        agent_ids = {s.agent_id for s in steps}
        result = await self.db.execute(
            select(AgentModel.id).where(AgentModel.id.in_(agent_ids))
        )
        found = set(result.scalars().all())
        missing = agent_ids - found
        if missing:
            raise ValidationError(f"agent_id not found: {', '.join(sorted(missing))}")
        for step in steps:
            for dep in step.depends_on:
                if dep not in keys:
                    raise ValidationError(f"depends_on references unknown step_key: {dep}")
            oc = _normalize_on_complete(getattr(step, "on_complete", None))
            if oc not in ("none", "notify", "confirm"):
                raise ValidationError("on_complete must be none|notify|confirm")
        depends_map = {s.step_key: list(s.depends_on) for s in steps}
        _validate_dag_acyclic(keys, depends_map)

    async def list_definitions(self) -> list[WorkflowDefinitionSummary]:
        step_count = (
            select(func.count())
            .select_from(WorkflowStepDefModel)
            .where(WorkflowStepDefModel.workflow_id == WorkflowDefinitionModel.id)
            .correlate(WorkflowDefinitionModel)
            .scalar_subquery()
        )
        result = await self.db.execute(
            select(WorkflowDefinitionModel, step_count.label("step_count")).order_by(
                WorkflowDefinitionModel.name
            )
        )
        items: list[WorkflowDefinitionSummary] = []
        for row, count in result.all():
            items.append(
                WorkflowDefinitionSummary(
                    id=row.id,
                    name=row.name,
                    title=row.title,
                    description=row.description,
                    tags=_tags_from_options(row.options),
                    step_count=count or 0,
                    created_at=row.created_at,
                )
            )
        return items

    async def get_definition(self, definition_id: str) -> WorkflowDefinitionRead:
        result = await self.db.execute(
            select(WorkflowDefinitionModel)
            .options(selectinload(WorkflowDefinitionModel.steps))
            .where(WorkflowDefinitionModel.id == definition_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise NotFoundError("WorkflowDefinition", definition_id)
        agent_ids = {s.agent_id for s in row.steps}
        names = await self._agent_names(agent_ids)
        return _definition_read(row, names)

    async def get_definition_by_name(self, name: str) -> WorkflowDefinitionRead:
        result = await self.db.execute(
            select(WorkflowDefinitionModel)
            .options(selectinload(WorkflowDefinitionModel.steps))
            .where(WorkflowDefinitionModel.name == name)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise NotFoundError("WorkflowDefinition", name)
        agent_ids = {s.agent_id for s in row.steps}
        names = await self._agent_names(agent_ids)
        return _definition_read(row, names)

    async def create_definition(self, data: WorkflowDefinitionCreate) -> WorkflowDefinitionRead:
        await self._validate_steps(data.steps)
        wf_id = new_id("wfd")
        row = WorkflowDefinitionModel(
            id=wf_id,
            name=data.name,
            title=data.title,
            description=data.description,
            options=_options_with_tags(data.options, data.tags, tags_provided=True),
        )
        self.db.add(row)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "NAME_EXISTS",
                f"Workflow name already exists: {data.name}",
            ) from exc
        for step in data.steps:
            self.db.add(
                WorkflowStepDefModel(
                    id=new_id("wfs"),
                    workflow_id=wf_id,
                    step_key=step.step_key,
                    label=step.label,
                    role=(step.role or "").strip(),
                    agent_id=step.agent_id,
                    depends_on=step.depends_on,
                    parallel=step.parallel,
                    on_complete=_normalize_on_complete(step.on_complete),
                    sort_order=step.sort_order,
                )
            )
        await self.db.flush()
        return await self.get_definition(wf_id)

    async def update_definition(
        self, definition_id: str, data: WorkflowDefinitionUpdate
    ) -> WorkflowDefinitionRead:
        result = await self.db.execute(
            select(WorkflowDefinitionModel)
            .options(selectinload(WorkflowDefinitionModel.steps))
            .where(WorkflowDefinitionModel.id == definition_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise NotFoundError("WorkflowDefinition", definition_id)

        updates = data.model_dump(exclude_unset=True)
        # Keep Pydantic step models for attribute access in _validate_steps / ORM insert.
        steps_payload = data.steps if "steps" in updates else None
        updates.pop("steps", None)
        tags_provided = "tags" in updates
        tags_payload = updates.pop("tags", None)
        options_provided = "options" in updates

        # Shallow-merge options so partial updates don't wipe flags like is_default_dev_plan.
        base_options = dict(row.options or {})
        if options_provided and updates.get("options") is not None:
            base_options = {**base_options, **(updates.pop("options") or {})}
        elif options_provided:
            updates.pop("options", None)

        if tags_provided or options_provided:
            row.options = _options_with_tags(
                base_options,
                tags_payload,
                tags_provided=tags_provided,
            )

        for key, value in updates.items():
            setattr(row, key, value)

        if steps_payload is not None:
            await self._validate_steps(steps_payload)
            row.steps.clear()
            await self.db.flush()
            for step in steps_payload:
                row.steps.append(
                    WorkflowStepDefModel(
                        id=new_id("wfs"),
                        workflow_id=definition_id,
                        step_key=step.step_key,
                        label=step.label,
                        role=(step.role or "").strip(),
                        agent_id=step.agent_id,
                        depends_on=step.depends_on,
                        parallel=step.parallel,
                        on_complete=_normalize_on_complete(step.on_complete),
                        sort_order=step.sort_order,
                    )
                )

        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "NAME_EXISTS",
                f"Workflow name already exists: {row.name}",
            ) from exc
        return await self.get_definition(definition_id)

    async def delete_definition(self, definition_id: str) -> None:
        row = await self.db.get(WorkflowDefinitionModel, definition_id)
        if not row:
            raise NotFoundError("WorkflowDefinition", definition_id)
        title = row.title
        await self.db.delete(row)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "WORKFLOW_IN_USE",
                f"无法删除工作流「{title}」：仍被运行实例引用",
            ) from exc
