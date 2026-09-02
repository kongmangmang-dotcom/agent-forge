"""今日计划 — DailyTask + TaskPlanItem；详细计划由工作流模板生成。"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.ids import new_id
from app.models.agent import AgentModel
from app.models.schedule import (
    DailyTaskModel,
    TaskMemoryModel,
    TaskNoteModel,
    TaskPlanItemModel,
)
from app.models.workflow import WorkflowDefinitionModel, WorkflowStepDefModel
from app.schemas.schedule import (
    DailyTaskCreate,
    DailyTaskRead,
    DailyTaskSummary,
    DailyTaskUpdate,
    DayOverview,
    DayOverviewRange,
    TaskAgentChatResponse,
    TaskMemoryCreate,
    TaskMemoryRead,
    TaskMemoryUpdate,
    TaskNoteCreate,
    TaskNoteRead,
    TaskNoteUpdate,
    TaskPlanItemRead,
    WorkflowPlanGroup,
)
from app.services.plan_progress_sync import (
    find_active_run_for_task,
    sync_plan_items_for_daily_task,
)

_DEV_PATTERN = re.compile(r"开发|实现|功能|修复|bug|接口|页面|登录|评审|PR|pr\b", re.I)
_TITLE_MAX = 80
_CONTEXT_MAX = 48_000
_NOTE_BODY_MAX = 16_000
_NOTE_SECTION_MAX = 40_000
_MEMORY_ITEM_MAX = 800
_MEMORY_SECTION_MAX = 4_000
_SAFE_NAME = re.compile(r"[^a-zA-Z0-9\-]+")


def _safe_doc_filename(title: str, note_id: str, index: int) -> str:
    base = _SAFE_NAME.sub("_", (title or "").strip()).strip("._") or f"note-{index}"
    base = base[:40].strip("_") or f"note-{index}"
    short_id = (note_id or "")[-6:] or str(index)
    return f"{index:02d}_{base}_{short_id}.md"


def _derive_title(requirement: str, fallback: str = "") -> str:
    text = (requirement or fallback or "").strip()
    if not text:
        return "未命名任务"
    first_line = text.splitlines()[0].strip()
    if len(first_line) <= _TITLE_MAX:
        return first_line
    return first_line[: _TITLE_MAX - 1].rstrip() + "…"


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


class ScheduleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _agent_names(self, agent_ids: set[str]) -> dict[str, str]:
        if not agent_ids:
            return {}
        result = await self.db.execute(
            select(AgentModel.id, AgentModel.name).where(AgentModel.id.in_(agent_ids))
        )
        return dict(result.all())

    async def _workflow_info(self, workflow_id: str | None) -> tuple[str | None, str | None]:
        if not workflow_id:
            return None, None
        row = await self.db.get(WorkflowDefinitionModel, workflow_id)
        if not row:
            return None, None
        return row.name, row.title

    def _item_read(self, item: TaskPlanItemModel, agent_names: dict[str, str]) -> TaskPlanItemRead:
        return TaskPlanItemRead(
            id=item.id,
            title=item.title,
            detail=item.detail,
            scheduled_time=item.scheduled_time,
            status=item.status,
            agent_id=item.agent_id,
            agent_name=agent_names.get(item.agent_id) if item.agent_id else None,
            linked_step_key=item.linked_step_key,
            workflow_definition_id=item.workflow_definition_id,
            sort_order=item.sort_order,
        )

    def _note_read(self, note: TaskNoteModel) -> TaskNoteRead:
        return TaskNoteRead(
            id=note.id,
            daily_task_id=note.daily_task_id,
            kind=note.kind,
            title=note.title or "",
            body=note.body or "",
            file_path=note.file_path or "",
            created_at=note.created_at,
            updated_at=note.updated_at,
        )

    def _memory_read(self, mem: TaskMemoryModel) -> TaskMemoryRead:
        tags = mem.tags if isinstance(mem.tags, list) else []
        return TaskMemoryRead(
            id=mem.id,
            daily_task_id=mem.daily_task_id,
            content=mem.content or "",
            tags=[str(t) for t in tags],
            pinned=bool(mem.pinned),
            created_at=mem.created_at,
            updated_at=mem.updated_at,
        )

    def _bound_ids(self, row: DailyTaskModel) -> list[str]:
        raw = row.bound_workflow_ids
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        for x in raw:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        return out

    def _ensure_bound(self, row: DailyTaskModel, workflow_id: str | None) -> None:
        if not workflow_id:
            return
        ids = self._bound_ids(row)
        if workflow_id not in ids:
            ids.append(workflow_id)
            row.bound_workflow_ids = ids

    async def _task_read(self, row: DailyTaskModel) -> DailyTaskRead:
        await sync_plan_items_for_daily_task(self.db, row.id)
        await self.db.refresh(row, attribute_names=["plan_items", "status", "updated_at"])

        agent_ids = {i.agent_id for i in row.plan_items if i.agent_id}
        names = await self._agent_names(agent_ids)
        wf_name, wf_title = await self._workflow_info(row.workflow_definition_id)
        notes = list(row.notes or [])
        memories = sorted(
            list(row.memories or []),
            key=lambda m: (0 if m.pinned else 1, m.created_at or datetime.now(timezone.utc)),
        )
        from app.models.workflow import WorkflowRunModel

        latest = (
            await self.db.execute(
                select(WorkflowRunModel)
                .where(WorkflowRunModel.daily_task_id == row.id)
                .order_by(WorkflowRunModel.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        active = await find_active_run_for_task(self.db, row.id)
        bound = self._bound_ids(row)
        if row.workflow_definition_id and row.workflow_definition_id not in bound:
            bound = [*bound, row.workflow_definition_id]

        plan_reads = [self._item_read(i, names) for i in row.plan_items]
        workflow_plans = await self._build_workflow_plans(row, bound, plan_reads)

        return DailyTaskRead(
            id=row.id,
            plan_date=row.plan_date,
            title=row.title,
            type=row.type,
            status=row.status,
            priority=row.priority,
            summary=row.summary,
            requirement=row.requirement or "",
            workflow_definition_id=row.workflow_definition_id,
            bound_workflow_ids=bound,
            workflow_name=wf_name,
            workflow_title=wf_title,
            active_workflow_run_id=active.id if active else None,
            latest_workflow_run_id=latest.id if latest else None,
            plan_author=row.plan_author,
            plan_updated_at=row.plan_updated_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            plan_items=plan_reads,
            workflow_plans=workflow_plans,
            notes=[self._note_read(n) for n in notes],
            memories=[self._memory_read(m) for m in memories],
        )

    async def _build_workflow_plans(
        self,
        row: DailyTaskModel,
        bound: list[str],
        plan_reads: list[TaskPlanItemRead],
    ) -> list[WorkflowPlanGroup]:
        from app.models.workflow import WorkflowRunModel

        # Group items; orphaned items (no wf id) attach to active if present.
        by_wf: dict[str, list[TaskPlanItemRead]] = {}
        for item in plan_reads:
            wid = item.workflow_definition_id or row.workflow_definition_id or ""
            if not wid:
                continue
            by_wf.setdefault(wid, []).append(item)

        order_ids = list(bound)
        for wid in by_wf:
            if wid not in order_ids:
                order_ids.append(wid)

        groups: list[WorkflowPlanGroup] = []
        for wid in order_ids:
            items = sorted(by_wf.get(wid, []), key=lambda x: x.sort_order)
            name, title = await self._workflow_info(wid)
            latest = (
                await self.db.execute(
                    select(WorkflowRunModel)
                    .where(
                        WorkflowRunModel.daily_task_id == row.id,
                        WorkflowRunModel.workflow_id == wid,
                    )
                    .order_by(WorkflowRunModel.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            active = (
                await self.db.execute(
                    select(WorkflowRunModel)
                    .where(
                        WorkflowRunModel.daily_task_id == row.id,
                        WorkflowRunModel.workflow_id == wid,
                        WorkflowRunModel.status.notin_(
                            ["completed", "failed", "cancelled"]
                        ),
                    )
                    .order_by(WorkflowRunModel.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            groups.append(
                WorkflowPlanGroup(
                    workflow_definition_id=wid,
                    workflow_name=name,
                    workflow_title=title,
                    is_active=wid == row.workflow_definition_id,
                    latest_run_id=latest.id if latest else None,
                    active_run_id=active.id if active else None,
                    plan_item_count=len(items),
                    plan_done_count=sum(1 for i in items if i.status == "done"),
                    plan_items=items,
                )
            )
        return groups

    async def list_tasks(self, plan_date: date | None = None) -> list[DailyTaskSummary]:
        day = plan_date or date.today()
        result = await self.db.execute(
            select(DailyTaskModel)
            .options(selectinload(DailyTaskModel.plan_items))
            .where(DailyTaskModel.plan_date == day)
            .order_by(DailyTaskModel.created_at.asc())
        )
        items: list[DailyTaskSummary] = []
        for row in result.scalars().all():
            await sync_plan_items_for_daily_task(self.db, row.id)
            await self.db.refresh(row, attribute_names=["plan_items", "status"])
            plan_items = row.plan_items or []
            wf_name, wf_title = await self._workflow_info(row.workflow_definition_id)
            bound = self._bound_ids(row)
            if row.workflow_definition_id and row.workflow_definition_id not in bound:
                bound = [*bound, row.workflow_definition_id]
            items.append(
                DailyTaskSummary(
                    id=row.id,
                    plan_date=row.plan_date,
                    title=row.title,
                    type=row.type,
                    status=row.status,
                    priority=row.priority,
                    summary=row.summary,
                    requirement=row.requirement or "",
                    workflow_definition_id=row.workflow_definition_id,
                    bound_workflow_ids=bound,
                    workflow_name=wf_name,
                    workflow_title=wf_title,
                    plan_item_count=len(plan_items),
                    plan_done_count=sum(1 for p in plan_items if p.status == "done"),
                    plan_author=row.plan_author,
                    plan_updated_at=row.plan_updated_at,
                    created_at=row.created_at,
                )
            )
        return items

    async def day_overview(self, plan_date: date | None = None) -> DayOverview:
        day = plan_date or date.today()
        items = await self.list_tasks(day)
        return DayOverview(
            plan_date=day,
            task_count=len(items),
            todo_count=sum(1 for t in items if t.status == "todo"),
            in_progress_count=sum(1 for t in items if t.status == "in_progress"),
            done_count=sum(1 for t in items if t.status == "done"),
            plan_item_count=sum(t.plan_item_count for t in items),
            plan_done_count=sum(t.plan_done_count for t in items),
        )

    async def day_overview_range(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        days: int = 14,
    ) -> DayOverviewRange:
        end = end_date or date.today()
        if start_date:
            start = start_date
        else:
            span = max(1, min(days, 90))
            start = end.fromordinal(end.toordinal() - (span - 1))
        if start > end:
            start, end = end, start

        # One query for tasks in range, then group in Python.
        result = await self.db.execute(
            select(DailyTaskModel)
            .options(selectinload(DailyTaskModel.plan_items))
            .where(
                DailyTaskModel.plan_date >= start,
                DailyTaskModel.plan_date <= end,
            )
            .order_by(DailyTaskModel.plan_date.asc())
        )
        by_day: dict[date, list[DailyTaskModel]] = {}
        for row in result.scalars().all():
            by_day.setdefault(row.plan_date, []).append(row)

        day_list: list[DayOverview] = []
        cursor = start
        while cursor <= end:
            rows = by_day.get(cursor, [])
            plan_items = [p for r in rows for p in (r.plan_items or [])]
            day_list.append(
                DayOverview(
                    plan_date=cursor,
                    task_count=len(rows),
                    todo_count=sum(1 for r in rows if r.status == "todo"),
                    in_progress_count=sum(1 for r in rows if r.status == "in_progress"),
                    done_count=sum(1 for r in rows if r.status == "done"),
                    plan_item_count=len(plan_items),
                    plan_done_count=sum(1 for p in plan_items if p.status == "done"),
                )
            )
            cursor = cursor.fromordinal(cursor.toordinal() + 1)

        return DayOverviewRange(
            start_date=start,
            end_date=end,
            days=day_list,
            total_task_count=sum(d.task_count for d in day_list),
            total_done_count=sum(d.done_count for d in day_list),
            total_plan_item_count=sum(d.plan_item_count for d in day_list),
            total_plan_done_count=sum(d.plan_done_count for d in day_list),
        )

    async def get_task(self, task_id: str) -> DailyTaskRead:
        result = await self.db.execute(
            select(DailyTaskModel)
            .options(
                selectinload(DailyTaskModel.plan_items),
                selectinload(DailyTaskModel.notes),
                selectinload(DailyTaskModel.memories),
            )
            .where(DailyTaskModel.id == task_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise NotFoundError("DailyTask", task_id)
        return await self._task_read(row)

    def _infer_type(self, title: str) -> str:
        return "dev" if _DEV_PATTERN.search(title) else "normal"

    async def _default_workflow_id(self) -> str | None:
        """只返回「标准开发计划」模板，不回退到其它工作流。"""
        result = await self.db.execute(
            select(WorkflowDefinitionModel.id)
            .where(WorkflowDefinitionModel.name == "dev-plan")
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _require_dev_plan_workflow_id(
        self, workflow_definition_id: str | None = None
    ) -> str:
        if workflow_definition_id:
            await self._ensure_workflow(workflow_definition_id)
            return workflow_definition_id
        wf_id = await self._default_workflow_id()
        if not wf_id:
            raise ValidationError(
                "未找到默认开发计划模板「标准开发计划」(dev-plan)，请先运行 seed_dev_plan_workflow"
            )
        return wf_id

    async def _ensure_workflow(self, workflow_id: str) -> WorkflowDefinitionModel:
        result = await self.db.execute(
            select(WorkflowDefinitionModel)
            .options(selectinload(WorkflowDefinitionModel.steps))
            .where(WorkflowDefinitionModel.id == workflow_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise ValidationError(f"workflow_definition_id not found: {workflow_id}")
        if not row.steps:
            raise ValidationError(f"工作流「{row.title}」没有步骤，无法生成计划表")
        return row

    async def _replace_plan_items(
        self, task: DailyTaskModel, _title: str, *, workflow_id: str | None = None
    ) -> None:
        """Replace plan items for one workflow template (default: active)."""
        wf_id = workflow_id or task.workflow_definition_id
        if not wf_id:
            raise ValidationError("生成开发计划前必须绑定工作流模板（默认：标准开发计划）")

        await self.db.execute(
            delete(TaskPlanItemModel).where(
                TaskPlanItemModel.daily_task_id == task.id,
                TaskPlanItemModel.workflow_definition_id == wf_id,
            )
        )
        # Also clear legacy rows without workflow_definition_id when regenerating active.
        if wf_id == task.workflow_definition_id:
            await self.db.execute(
                delete(TaskPlanItemModel).where(
                    TaskPlanItemModel.daily_task_id == task.id,
                    TaskPlanItemModel.workflow_definition_id.is_(None),
                )
            )
        await self.db.flush()

        wf = await self._ensure_workflow(wf_id)
        agent_names = await self._agent_names({s.agent_id for s in wf.steps})
        for index, step in enumerate(wf.steps):
            deps = step.depends_on or []
            dep_text = f"依赖: {', '.join(deps)}" if deps else "无前置依赖"
            agent_label = agent_names.get(step.agent_id, step.agent_id)
            self.db.add(
                TaskPlanItemModel(
                    id=new_id("tpi"),
                    daily_task_id=task.id,
                    sort_order=step.sort_order if step.sort_order is not None else index,
                    scheduled_time=None,
                    title=step.label,
                    detail=(
                        f"工作流步骤 `{step.step_key}` · Agent: {agent_label} · {dep_text}"
                        f"{' · 并行' if step.parallel else ''}"
                    ),
                    status="todo",
                    agent_id=step.agent_id,
                    linked_step_key=step.step_key,
                    workflow_definition_id=wf_id,
                )
            )
        self._ensure_bound(task, wf_id)
        task.plan_author = f"workflow:{wf.name}"
        task.type = "dev"
        task.summary = f"开发计划（{wf.title}）"
        task.plan_updated_at = datetime.now(timezone.utc)

    async def _ensure_plans_for_bound(self, task: DailyTaskModel) -> None:
        """Ensure every bound workflow has a plan table; drop plans for unbound templates."""
        bound = self._bound_ids(task)
        existing = (
            await self.db.execute(
                select(TaskPlanItemModel.workflow_definition_id)
                .where(TaskPlanItemModel.daily_task_id == task.id)
                .distinct()
            )
        ).scalars().all()
        existing_ids = {x for x in existing if x}

        for wid in list(existing_ids):
            if wid not in bound:
                await self.db.execute(
                    delete(TaskPlanItemModel).where(
                        TaskPlanItemModel.daily_task_id == task.id,
                        TaskPlanItemModel.workflow_definition_id == wid,
                    )
                )

        for wid in bound:
            has_items = (
                await self.db.execute(
                    select(TaskPlanItemModel.id)
                    .where(
                        TaskPlanItemModel.daily_task_id == task.id,
                        TaskPlanItemModel.workflow_definition_id == wid,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not has_items:
                await self._replace_plan_items(task, task.title, workflow_id=wid)

        await self.db.flush()

    async def create_task(self, data: DailyTaskCreate) -> DailyTaskRead:
        if data.with_plan:
            task_type = "dev"
            wf_id = await self._require_dev_plan_workflow_id(data.workflow_definition_id)
        else:
            task_type = data.type if data.type in ("normal", "dev") else self._infer_type(data.title)
            wf_id = data.workflow_definition_id
            if wf_id:
                await self._ensure_workflow(wf_id)

        requirement = (data.requirement or "").strip()
        title = data.title.strip() or _derive_title(requirement)
        row = DailyTaskModel(
            id=new_id("tsk"),
            plan_date=data.plan_date or date.today(),
            title=title,
            type=task_type,
            status="todo",
            priority=data.priority if data.priority in ("high", "medium", "low") else "medium",
            summary=data.summary.strip(),
            requirement=requirement,
            workflow_definition_id=wf_id,
            bound_workflow_ids=[wf_id] if wf_id else [],
        )
        self.db.add(row)
        await self.db.flush()

        if data.with_plan:
            await self._replace_plan_items(row, row.title)
        else:
            self.db.add(
                TaskPlanItemModel(
                    id=new_id("tpi"),
                    daily_task_id=row.id,
                    sort_order=0,
                    title=row.title,
                    detail="手动添加的任务。可绑定「标准开发计划」后生成开发计划表。",
                    status="todo",
                )
            )
            row.plan_updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        return await self.get_task(row.id)

    async def update_task(self, task_id: str, data: DailyTaskUpdate) -> DailyTaskRead:
        result = await self.db.execute(
            select(DailyTaskModel)
            .options(selectinload(DailyTaskModel.plan_items))
            .where(DailyTaskModel.id == task_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise NotFoundError("DailyTask", task_id)

        updates = data.model_dump(exclude_unset=True)
        if "status" in updates and updates["status"] not in ("todo", "in_progress", "done"):
            raise ValidationError("status must be todo|in_progress|done")
        if "type" in updates and updates["type"] not in ("normal", "dev"):
            raise ValidationError("type must be normal|dev")
        if "workflow_definition_id" in updates and updates["workflow_definition_id"]:
            await self._ensure_workflow(updates["workflow_definition_id"])
        if "bound_workflow_ids" in updates and updates["bound_workflow_ids"] is not None:
            cleaned: list[str] = []
            for wid in updates["bound_workflow_ids"]:
                s = str(wid).strip()
                if not s or s in cleaned:
                    continue
                await self._ensure_workflow(s)
                cleaned.append(s)
            updates["bound_workflow_ids"] = cleaned
            active = updates.get("workflow_definition_id", row.workflow_definition_id)
            if active and active not in cleaned:
                raise ValidationError("当前激活工作流必须包含在已绑定列表中")
        for key, value in updates.items():
            setattr(row, key, value)
        if row.workflow_definition_id:
            self._ensure_bound(row, row.workflow_definition_id)
        if "bound_workflow_ids" in updates or "workflow_definition_id" in updates:
            await self._ensure_plans_for_bound(row)
        await self.db.flush()
        return await self.get_task(task_id)

    async def delete_task(self, task_id: str) -> None:
        row = await self.db.get(DailyTaskModel, task_id)
        if not row:
            raise NotFoundError("DailyTask", task_id)
        await self.db.delete(row)
        await self.db.flush()

    async def regenerate_plan(
        self, task_id: str, workflow_definition_id: str | None = None
    ) -> DailyTaskRead:
        result = await self.db.execute(
            select(DailyTaskModel)
            .options(selectinload(DailyTaskModel.plan_items))
            .where(DailyTaskModel.id == task_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise NotFoundError("DailyTask", task_id)

        if workflow_definition_id is not None:
            row.workflow_definition_id = await self._require_dev_plan_workflow_id(
                workflow_definition_id or None
            )
        elif not row.workflow_definition_id:
            row.workflow_definition_id = await self._require_dev_plan_workflow_id(None)

        self._ensure_bound(row, row.workflow_definition_id)
        row.type = "dev"
        await self._replace_plan_items(row, row.title, workflow_id=row.workflow_definition_id)
        if row.status == "todo":
            row.status = "in_progress"
        await self.db.flush()
        return await self.get_task(task_id)

    async def plan_today(
        self,
        goal: str,
        plan_date: date | None = None,
        workflow_definition_id: str | None = None,
    ) -> DailyTaskRead:
        """仅生成开发计划：固定 type=dev，默认绑定「标准开发计划」模板。"""
        requirement = goal.strip()
        wf_id = await self._require_dev_plan_workflow_id(workflow_definition_id)
        wf_name, wf_title = await self._workflow_info(wf_id)
        created = await self.create_task(
            DailyTaskCreate(
                title=_derive_title(requirement),
                type="dev",
                summary=f"开发计划（{wf_title or wf_name or 'dev'}）",
                requirement=requirement,
                plan_date=plan_date or date.today(),
                workflow_definition_id=wf_id,
                with_plan=True,
            )
        )
        return await self.update_task(created.id, DailyTaskUpdate(status="in_progress"))

    async def start_task_workflow(
        self,
        task_id: str,
        task_prompt: str | None = None,
        workflow_definition_id: str | None = None,
    ):
        from app.models.workflow import WorkflowRunModel
        from app.services.orchestrator import OrchestratorService

        task = await self.get_task(task_id)
        active = await find_active_run_for_task(self.db, task_id)
        if active:
            raise ConflictError(
                "WORKFLOW_ALREADY_RUNNING",
                f"该任务已有进行中的工作流运行（{active.id}），请先完成或终止后再启动",
            )

        row = await self.db.get(DailyTaskModel, task_id)
        if not row:
            raise NotFoundError("DailyTask", task_id)

        if workflow_definition_id:
            await self._ensure_workflow(workflow_definition_id)
            bound = self._bound_ids(row)
            if bound and workflow_definition_id not in bound:
                raise ValidationError("只能启动已绑定的工作流模板")
            if row.workflow_definition_id != workflow_definition_id:
                row.workflow_definition_id = workflow_definition_id
                self._ensure_bound(row, workflow_definition_id)
                await self._replace_plan_items(row, row.title)
                await self.db.flush()
                task = await self.get_task(task_id)
            else:
                self._ensure_bound(row, workflow_definition_id)

        if not task.workflow_definition_id:
            raise ValidationError("该任务未绑定工作流模板")
        workspace = await self._workspace_for_workflow(task.workflow_definition_id)
        prompt = self._build_start_prompt(task, task_prompt, workspace_path=workspace)
        orch = OrchestratorService(self.db)
        run = await orch.start_workflow(
            task.workflow_definition_id,
            prompt,
            workspace_path=workspace,
        )
        wf_run = await self.db.get(WorkflowRunModel, run.id)
        if wf_run:
            wf_run.daily_task_id = task_id
            await self.db.flush()
            from app.services.plan_progress_sync import sync_plan_items_from_workflow_run

            await sync_plan_items_from_workflow_run(self.db, wf_run.id)
        await self.update_task(task_id, DailyTaskUpdate(status="in_progress"))
        return await orch.get_run(run.id)

    async def agent_chat(
        self,
        task_id: str,
        *,
        agent_id: str,
        message: str,
        run_id: str | None = None,
        new_session: bool = False,
    ) -> TaskAgentChatResponse:
        """Direct Agent conversation for a DailyTask.

        First turn of a session attaches existing markdown docs; follow-ups do not
        (process inject when possible, otherwise continue with chat history only).
        """
        from app.domain.enums import RunStatus
        from app.models.run import AgentRunModel
        from app.services.run_service import RunService

        message = (message or "").strip()
        if not message:
            raise ValidationError("message 不能为空")

        task = await self.get_task(task_id)
        agent = await self.db.get(AgentModel, agent_id)
        if not agent:
            raise NotFoundError("Agent", agent_id)

        run_svc = RunService(self.db)
        _TERMINAL = {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }

        # 1) Prefer inject into an active run for this task+agent.
        running: AgentRunModel | None = None
        if run_id:
            candidate = await self.db.get(AgentRunModel, run_id)
            if (
                candidate
                and candidate.daily_task_id == task_id
                and candidate.agent_id == agent_id
                and candidate.status not in _TERMINAL
            ):
                running = candidate
        if running is None and not new_session:
            running = (
                await self.db.execute(
                    select(AgentRunModel)
                    .where(
                        AgentRunModel.daily_task_id == task_id,
                        AgentRunModel.agent_id == agent_id,
                        AgentRunModel.status.notin_(list(_TERMINAL)),
                    )
                    .order_by(AgentRunModel.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        if running is not None:
            if running.status == RunStatus.PENDING:
                raise ConflictError("AGENT_BUSY", "Agent 正在启动，请稍后再发")
            can_inject = await self._provider_supports_stdin_inject(self.db, agent)
            if can_inject and running.status == RunStatus.RUNNING:
                try:
                    await run_svc.inject_message(running.id, message)
                    if task.status == "todo":
                        await self.update_task(task_id, DailyTaskUpdate(status="in_progress"))
                    return TaskAgentChatResponse(
                        run_id=running.id,
                        agent_id=agent_id,
                        status=running.status,
                        created=False,
                        mode="inject",
                        docs_attached=False,
                    )
                except ConflictError:
                    # Process already gone — fall through to continue/start.
                    pass
            elif running.status == RunStatus.RUNNING and not can_inject:
                raise ConflictError(
                    "AGENT_BUSY",
                    "当前轮次进行中；结束后再发送将自动延续上下文（不再附带文档）",
                )

        workspace = (agent.workspace_path or "").strip() or "workspace/demo"
        prior_ids = await self._prior_task_agent_run_ids(task_id, agent_id)
        attach_docs = new_session or not prior_ids

        if attach_docs:
            prompt = self._build_start_prompt(task, message, workspace_path=workspace)
            mode = "start"
        else:
            history = await self._load_task_agent_history(prior_ids)
            if history:
                prompt = (
                    f"{message}\n\n"
                    f"--- 同 Agent 历史对话（延续上下文，文档已在首轮提供） ---\n"
                    f"{_truncate(history, 12000)}"
                )
            else:
                prompt = message
            mode = "continue"

        row = await run_svc.create_and_start(
            agent_id,
            prompt,
            daily_task_id=task_id,
            workspace_path=workspace,
            display_message=message,
        )
        if task.status == "todo":
            await self.update_task(task_id, DailyTaskUpdate(status="in_progress"))
        return TaskAgentChatResponse(
            run_id=row.id,
            agent_id=agent_id,
            status=row.status,
            created=True,
            mode=mode,
            docs_attached=attach_docs,
        )

    async def _prior_task_agent_run_ids(self, task_id: str, agent_id: str) -> list[str]:
        from app.models.run import AgentRunModel

        rows = (
            await self.db.execute(
                select(AgentRunModel.id)
                .where(
                    AgentRunModel.daily_task_id == task_id,
                    AgentRunModel.agent_id == agent_id,
                )
                .order_by(AgentRunModel.created_at.asc())
            )
        ).scalars().all()
        return list(rows)

    async def _load_task_agent_history(self, agent_run_ids: list[str]) -> str:
        from app.models.run import AgentMessageModel

        if not agent_run_ids:
            return ""
        # Keep last few runs to bound prompt size.
        recent = agent_run_ids[-6:]
        blocks: list[str] = []
        for rid in recent:
            msgs = (
                await self.db.execute(
                    select(AgentMessageModel)
                    .where(
                        AgentMessageModel.run_id == rid,
                        AgentMessageModel.role.in_(("user", "assistant")),
                    )
                    .order_by(AgentMessageModel.created_at.asc())
                )
            ).scalars().all()
            if not msgs:
                continue
            lines = [f"## 会话 {rid}"]
            for m in msgs:
                content = (m.content or "").strip()
                if not content:
                    continue
                if m.role == "user" and (
                    "任务已有 Markdown" in content or "同 Agent 历史对话" in content
                ):
                    # Prefer the short display portion already stored; otherwise truncate.
                    content = _truncate(content.split("\n\n---", 1)[0].strip() or content, 600)
                lines.append(f"[{m.role}]\n{_truncate(content, 1200)}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    async def get_latest_agent_chat_run(
        self, task_id: str, agent_id: str | None = None
    ):
        from app.models.run import AgentRunModel
        from app.services.run_service import RunService

        await self._require_task(task_id)
        q = select(AgentRunModel).where(AgentRunModel.daily_task_id == task_id)
        if agent_id:
            q = q.where(AgentRunModel.agent_id == agent_id)
        row = (
            await self.db.execute(q.order_by(AgentRunModel.created_at.desc()).limit(1))
        ).scalar_one_or_none()
        if not row:
            return None
        return await RunService(self.db).get_run(row.id)

    @staticmethod
    async def _provider_supports_stdin_inject(db: AsyncSession, agent: AgentModel) -> bool:
        """Codex CLI (uses_stdin=False) cannot receive mid-run follow-ups via stdin."""
        from app.models.provider import ProviderModel
        from app.providers.registry import registry

        provider = await db.get(ProviderModel, agent.provider_id)
        if not provider:
            return True
        impl = registry.get(provider.kind)
        if impl is None:
            return True
        return bool(getattr(impl, "uses_stdin", True))

    async def _workspace_for_workflow(self, workflow_id: str) -> str:
        """Prefer the first step agent's workspace so markdown paths resolve correctly."""
        steps = (
            await self.db.execute(
                select(WorkflowStepDefModel)
                .where(WorkflowStepDefModel.workflow_id == workflow_id)
                .order_by(WorkflowStepDefModel.sort_order)
            )
        ).scalars().all()
        for step in steps:
            if not step.agent_id:
                continue
            agent = await self.db.get(AgentModel, step.agent_id)
            if agent and (agent.workspace_path or "").strip():
                return agent.workspace_path.strip()
        return "workspace/demo"

    def _markdown_note_body(self, note: TaskNoteRead, workspace_path: str) -> str:
        """Prefer stored body; otherwise read .md from disk via file_path."""
        from app.services.task_note_sync import _is_markdown_path, _read_markdown_body

        body = (note.body or "").strip()
        path = (note.file_path or "").strip()
        if body:
            return _truncate(body, _NOTE_BODY_MAX)
        if path and _is_markdown_path(path):
            loaded = _read_markdown_body(workspace_path, path).strip()
            if loaded:
                return _truncate(loaded, _NOTE_BODY_MAX)
        return ""

    def _materialize_task_docs(
        self,
        task: DailyTaskRead,
        workspace_path: str,
    ) -> list[tuple[str, str]]:
        """把任务 Markdown 笔记写入工作区真实文件，返回 [(相对路径, 标题), ...]。"""
        from pathlib import Path

        from app.services.task_note_sync import _is_markdown_path

        root = Path(workspace_path or ".")
        docs_dir = root / ".agentforge" / "task-docs" / task.id
        docs_dir.mkdir(parents=True, exist_ok=True)
        written: list[tuple[str, str]] = []
        for i, n in enumerate(task.notes or [], start=1):
            title = (n.title or "").strip() or f"笔记{i}"
            path = (n.file_path or "").strip()
            is_md = (
                n.kind == "markdown"
                or (path and _is_markdown_path(path))
                or bool((n.body or "").strip())
            )
            content = self._markdown_note_body(n, workspace_path) if is_md else ""
            if not content:
                continue
            fname = _safe_doc_filename(title, n.id, i)
            out = docs_dir / fname
            header = f"# {title}\n\n"
            if path:
                header += f"> 来源路径: `{path}`\n\n"
            out.write_text(header + content, encoding="utf-8")
            try:
                rel = out.relative_to(root).as_posix()
            except ValueError:
                rel = str(out)
            written.append((rel, title))
        return written

    def _build_start_prompt(
        self,
        task: DailyTaskRead,
        task_prompt: str | None = None,
        *,
        workspace_path: str = ".",
    ) -> str:
        parts: list[str] = []
        primary = (task_prompt or task.requirement or task.summary or task.title or "").strip()
        if primary:
            parts.append(primary)

        pinned = [m for m in task.memories if m.pinned and m.content.strip()]
        others = [m for m in task.memories if not m.pinned and m.content.strip()]
        mem_lines: list[str] = []
        for m in pinned + others:
            mem_lines.append(f"- {_truncate(m.content, _MEMORY_ITEM_MAX)}")
        if mem_lines:
            parts.append(
                "--- Agent 记忆 ---\n"
                + _truncate("\n".join(mem_lines), _MEMORY_SECTION_MAX)
            )

        # 文档写入工作区文件，prompt 只引用路径（避免 CLI argv/上下文膨胀）
        from app.services.task_note_sync import _is_markdown_path

        doc_files = self._materialize_task_docs(task, workspace_path)
        other_note_lines: list[str] = []
        for n in task.notes:
            title = (n.title or "").strip() or "(无标题)"
            path = (n.file_path or "").strip()
            is_md = (
                n.kind == "markdown"
                or (path and _is_markdown_path(path))
                or bool((n.body or "").strip())
            )
            content = self._markdown_note_body(n, workspace_path) if is_md else ""
            if content:
                continue  # 已物化为工作区文件
            if path:
                other_note_lines.append(f"- [文件] {title}: {path}")
            elif (n.body or "").strip():
                other_note_lines.append(
                    f"- [笔记] {title}:\n{_truncate(n.body.strip(), _NOTE_BODY_MAX)}"
                )

        if doc_files:
            lines = [f"- `{rel}` — {title}" for rel, title in doc_files]
            parts.append(
                "--- 任务文档（已写入工作区，请直接打开这些文件阅读/修改） ---\n"
                + "\n".join(lines)
                + "\n\n请基于上述文件完成本步骤；需要改文档时直接编辑对应 md 并保存。"
            )
        if other_note_lines:
            parts.append("--- 其它任务笔记/文件 ---\n" + "\n".join(other_note_lines))

        joined = "\n\n".join(parts).strip()
        return _truncate(joined, _CONTEXT_MAX) if joined else task.title

    async def _require_task(self, task_id: str) -> DailyTaskModel:
        row = await self.db.get(DailyTaskModel, task_id)
        if not row:
            raise NotFoundError("DailyTask", task_id)
        return row

    async def create_note(self, task_id: str, data: TaskNoteCreate) -> TaskNoteRead:
        await self._require_task(task_id)
        kind = data.kind if data.kind in ("markdown", "file") else "markdown"
        if kind == "file" and not (data.file_path or "").strip() and not (data.body or "").strip():
            raise ValidationError("文件类笔记需要填写 file_path 或说明")
        note = TaskNoteModel(
            id=new_id("tn"),
            daily_task_id=task_id,
            kind=kind,
            title=(data.title or "").strip(),
            body=(data.body or "").strip(),
            file_path=(data.file_path or "").strip(),
        )
        self.db.add(note)
        await self.db.flush()
        return self._note_read(note)

    async def update_note(self, task_id: str, note_id: str, data: TaskNoteUpdate) -> TaskNoteRead:
        result = await self.db.execute(
            select(TaskNoteModel).where(
                TaskNoteModel.id == note_id,
                TaskNoteModel.daily_task_id == task_id,
            )
        )
        note = result.scalar_one_or_none()
        if not note:
            raise NotFoundError("TaskNote", note_id)
        updates = data.model_dump(exclude_unset=True)
        if "kind" in updates and updates["kind"] not in ("markdown", "file"):
            raise ValidationError("kind must be markdown|file")
        for key, value in updates.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(note, key, value)
        await self.db.flush()
        return self._note_read(note)

    async def delete_note(self, task_id: str, note_id: str) -> None:
        result = await self.db.execute(
            select(TaskNoteModel).where(
                TaskNoteModel.id == note_id,
                TaskNoteModel.daily_task_id == task_id,
            )
        )
        note = result.scalar_one_or_none()
        if not note:
            raise NotFoundError("TaskNote", note_id)
        await self.db.delete(note)
        await self.db.flush()

    async def create_memory(self, task_id: str, data: TaskMemoryCreate) -> TaskMemoryRead:
        await self._require_task(task_id)
        content = data.content.strip()
        if not content:
            raise ValidationError("记忆内容不能为空")
        mem = TaskMemoryModel(
            id=new_id("tm"),
            daily_task_id=task_id,
            content=content,
            tags=[str(t).strip() for t in (data.tags or []) if str(t).strip()],
            pinned=bool(data.pinned),
        )
        self.db.add(mem)
        await self.db.flush()
        return self._memory_read(mem)

    async def update_memory(
        self, task_id: str, memory_id: str, data: TaskMemoryUpdate
    ) -> TaskMemoryRead:
        result = await self.db.execute(
            select(TaskMemoryModel).where(
                TaskMemoryModel.id == memory_id,
                TaskMemoryModel.daily_task_id == task_id,
            )
        )
        mem = result.scalar_one_or_none()
        if not mem:
            raise NotFoundError("TaskMemory", memory_id)
        updates = data.model_dump(exclude_unset=True)
        if "content" in updates:
            updates["content"] = (updates["content"] or "").strip()
            if not updates["content"]:
                raise ValidationError("记忆内容不能为空")
        if "tags" in updates and updates["tags"] is not None:
            updates["tags"] = [str(t).strip() for t in updates["tags"] if str(t).strip()]
        for key, value in updates.items():
            setattr(mem, key, value)
        await self.db.flush()
        return self._memory_read(mem)

    async def delete_memory(self, task_id: str, memory_id: str) -> None:
        result = await self.db.execute(
            select(TaskMemoryModel).where(
                TaskMemoryModel.id == memory_id,
                TaskMemoryModel.daily_task_id == task_id,
            )
        )
        mem = result.scalar_one_or_none()
        if not mem:
            raise NotFoundError("TaskMemory", memory_id)
        await self.db.delete(mem)
        await self.db.flush()