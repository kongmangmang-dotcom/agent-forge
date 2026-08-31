"""DAG 工作流编排器 — 驱动 StepRun → AgentRun → Provider。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import new_id
from app.domain.enums import RunStatus
from app.models.agent import AgentModel
from app.models.run import AgentMessageModel, AgentRunModel
from app.models.workflow import (
    StepRunModel,
    WorkflowDefinitionModel,
    WorkflowRunModel,
    WorkflowStepDefModel,
)
from app.schemas.workflow import (
    WorkflowLinkedNote,
    WorkflowRunRead,
    WorkflowRunSummary,
    WorkflowStepRunRead,
    WorkflowTerminatePreview,
    WorkflowTerminateResult,
)
from app.services.run_service import RunService
from app.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)

_orchestrator_tasks: dict[str, asyncio.Task] = {}

_TERMINAL = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
)


_SUMMARY_MAX_CHARS = 1200
_UPSTREAM_TOTAL_MAX_CHARS = 3600
_HISTORY_MAX_CHARS = 12000
_REUSE_SAME_AGENT_OPTION = "reuse_same_agent_session"


def _ready_step_keys(
    step_defs: list[WorkflowStepDefModel],
    status_by_key: dict[str, str],
) -> list[WorkflowStepDefModel]:
    completed = {k for k, s in status_by_key.items() if s == RunStatus.COMPLETED}
    ready: list[WorkflowStepDefModel] = []
    for step in step_defs:
        current = status_by_key.get(step.step_key, RunStatus.PENDING)
        if current != RunStatus.PENDING:
            continue
        if all(dep in completed for dep in (step.depends_on or [])):
            ready.append(step)
    return ready


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20].rstrip() + "\n…(已截断)"


def _build_step_prompt(
    global_task: str,
    step_label: str,
    step_key: str,
    upstream: list[tuple[str, str, str]],
    *,
    conversation_history: str = "",
) -> str:
    """upstream: list of (step_key, label, summary)."""
    parts = [global_task.strip()]
    if conversation_history.strip():
        parts.append(
            "\n--- 同 Agent 历史对话（延续上下文）---\n"
            + _truncate(conversation_history, _HISTORY_MAX_CHARS)
        )
    if upstream:
        lines = ["\n--- 上游步骤摘要 ---"]
        used = 0
        for key, label, summary in upstream:
            if not summary.strip():
                continue
            chunk = _truncate(summary, _SUMMARY_MAX_CHARS)
            block = f"\n[{key}] {label}\n{chunk}"
            if used + len(block) > _UPSTREAM_TOTAL_MAX_CHARS:
                lines.append("\n…(其余上游摘要已省略)")
                break
            lines.append(block)
            used += len(block)
        if len(lines) > 1:
            parts.append("".join(lines))
    continue_hint = (
        "请在延续上述同 Agent 对话的基础上完成本步骤。"
        if conversation_history.strip()
        else "请结合上游摘要完成本步骤职责，输出简要结果。"
    )
    parts.append(
        f"\n--- 当前工作流步骤 ---\n"
        f"步骤: {step_label} ({step_key})\n"
        f"{continue_hint}"
    )
    return "\n".join(parts)


async def _extract_run_summary(session: AsyncSession, agent_run_id: str) -> str:
    result = await session.execute(
        select(AgentMessageModel)
        .where(
            AgentMessageModel.run_id == agent_run_id,
            AgentMessageModel.role == "assistant",
        )
        .order_by(AgentMessageModel.created_at.asc())
    )
    messages = list(result.scalars().all())
    texts = [m.content.strip() for m in messages if m.content and m.content.strip()]
    if not texts:
        return ""
    # Prefer the last substantial assistant message; fall back to joined text.
    primary = max(texts, key=len)
    if len(primary) >= 40:
        return _truncate(primary, _SUMMARY_MAX_CHARS)
    return _truncate("\n\n".join(texts), _SUMMARY_MAX_CHARS)


async def _workflow_reuses_same_agent_session(session: AsyncSession, workflow_id: str) -> bool:
    wf = await session.get(WorkflowDefinitionModel, workflow_id)
    options = (wf.options or {}) if wf else {}
    return bool(options.get(_REUSE_SAME_AGENT_OPTION))


async def _prior_same_agent_run_ids(
    session: AsyncSession,
    *,
    workflow_run_id: str,
    agent_id: str,
    current_step_key: str,
) -> list[str]:
    """Completed steps in this workflow run that used the same agent, oldest first."""
    result = await session.execute(
        select(StepRunModel)
        .where(
            StepRunModel.workflow_run_id == workflow_run_id,
            StepRunModel.agent_id == agent_id,
            StepRunModel.status == RunStatus.COMPLETED,
            StepRunModel.step_key != current_step_key,
            StepRunModel.agent_run_id.is_not(None),
        )
        .order_by(StepRunModel.finished_at.asc().nulls_last(), StepRunModel.started_at.asc())
    )
    return [s.agent_run_id for s in result.scalars().all() if s.agent_run_id]


async def _load_conversation_history(session: AsyncSession, agent_run_ids: list[str]) -> str:
    if not agent_run_ids:
        return ""
    blocks: list[str] = []
    for run_id in agent_run_ids:
        result = await session.execute(
            select(AgentMessageModel)
            .where(
                AgentMessageModel.run_id == run_id,
                AgentMessageModel.role.in_(("user", "assistant")),
            )
            .order_by(AgentMessageModel.created_at.asc())
        )
        msgs = list(result.scalars().all())
        if not msgs:
            continue
        lines = [f"## 会话片段 {run_id}"]
        for m in msgs:
            content = (m.content or "").strip()
            if not content:
                continue
            # Avoid re-embedding nested history blocks from prior continued prompts.
            if m.role == "user" and "同 Agent 历史对话" in content:
                # Keep only the current-step portion if present.
                marker = "--- 当前工作流步骤 ---"
                if marker in content:
                    content = content.split(marker, 1)[-1].strip()
                    content = f"(续写任务)\n{content}"
                else:
                    content = _truncate(content, 400)
            lines.append(f"[{m.role}]\n{_truncate(content, _SUMMARY_MAX_CHARS)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


class OrchestratorService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_workflow(
        self,
        definition_id: str,
        task_prompt: str,
        workspace_path: str = "",
    ) -> WorkflowRunModel:
        definition = await WorkflowService(self.db).get_definition(definition_id)
        if not definition.steps:
            raise ValidationError("Workflow has no steps")

        wfr_id = new_id("wfr")
        row = WorkflowRunModel(
            id=wfr_id,
            workflow_id=definition_id,
            status=RunStatus.PENDING,
            progress=0,
            input={
                "task_prompt": task_prompt,
                "workspace_path": workspace_path.strip(),
            },
        )
        self.db.add(row)
        await self.db.flush()

        for step in definition.steps:
            self.db.add(
                StepRunModel(
                    id=new_id("stp"),
                    workflow_run_id=wfr_id,
                    step_key=step.step_key,
                    agent_id=step.agent_id,
                    status=RunStatus.PENDING,
                )
            )
        await self.db.flush()
        await self.db.commit()

        task = asyncio.create_task(_orchestrate_workflow(wfr_id))
        _orchestrator_tasks[wfr_id] = task
        return row

    async def list_runs(self, status: str | None = None) -> list[WorkflowRunSummary]:
        q = (
            select(WorkflowRunModel, WorkflowDefinitionModel.title)
            .join(
                WorkflowDefinitionModel,
                WorkflowRunModel.workflow_id == WorkflowDefinitionModel.id,
            )
            .order_by(WorkflowRunModel.created_at.desc())
            .limit(50)
        )
        if status:
            q = q.where(WorkflowRunModel.status == status)
        result = await self.db.execute(q)
        items: list[WorkflowRunSummary] = []
        for row, title in result.all():
            task_prompt = str((row.input or {}).get("task_prompt", ""))
            note_count = await self._linked_note_count(row)
            items.append(
                WorkflowRunSummary(
                    id=row.id,
                    workflow_id=row.workflow_id,
                    workflow_title=title,
                    status=row.status,
                    progress=row.progress,
                    task_prompt=task_prompt,
                    daily_task_id=row.daily_task_id,
                    linked_note_count=note_count,
                    started_at=row.started_at,
                    created_at=row.created_at,
                )
            )
        return items

    async def _agent_run_ids_for_workflow(self, workflow_run_id: str) -> list[str]:
        result = await self.db.execute(
            select(StepRunModel.agent_run_id).where(
                StepRunModel.workflow_run_id == workflow_run_id,
                StepRunModel.agent_run_id.is_not(None),
            )
        )
        return [rid for rid in result.scalars().all() if rid]

    async def _linked_notes_for_workflow(
        self, wf_run: WorkflowRunModel
    ) -> list[WorkflowLinkedNote]:
        from app.models.run import FileChangeModel
        from app.models.schedule import TaskNoteModel

        if not wf_run.daily_task_id:
            return []

        agent_run_ids = await self._agent_run_ids_for_workflow(wf_run.id)
        path_keys: set[str] = set()
        if agent_run_ids:
            fc = await self.db.execute(
                select(FileChangeModel.path).where(FileChangeModel.run_id.in_(agent_run_ids))
            )
            for p in fc.scalars().all():
                if p and str(p).lower().endswith((".md", ".markdown", ".mdx")):
                    path_keys.add(str(p).replace("\\", "/"))

        notes_result = await self.db.execute(
            select(TaskNoteModel).where(TaskNoteModel.daily_task_id == wf_run.daily_task_id)
        )
        linked: list[WorkflowLinkedNote] = []
        for note in notes_result.scalars().all():
            fp = (note.file_path or "").replace("\\", "/")
            body = note.body or ""
            matched = False
            if fp and fp in path_keys:
                matched = True
            elif any(rid and rid in body for rid in agent_run_ids):
                matched = True
            if matched:
                linked.append(
                    WorkflowLinkedNote(
                        id=note.id,
                        title=note.title or fp or note.id,
                        file_path=fp,
                    )
                )
        return linked

    async def _linked_note_count(self, wf_run: WorkflowRunModel) -> int:
        return len(await self._linked_notes_for_workflow(wf_run))

    async def terminate_preview(self, workflow_run_id: str) -> WorkflowTerminatePreview:
        row = await self.db.get(WorkflowRunModel, workflow_run_id)
        if not row:
            raise NotFoundError("WorkflowRun", workflow_run_id)
        notes = await self._linked_notes_for_workflow(row)
        return WorkflowTerminatePreview(
            workflow_run_id=row.id,
            daily_task_id=row.daily_task_id,
            status=row.status,
            note_count=len(notes),
            notes=notes,
        )

    async def terminate_workflow(
        self,
        workflow_run_id: str,
        *,
        delete_notes: bool = False,
        delete_record: bool = True,
    ) -> WorkflowTerminateResult:
        result = await self.db.execute(
            select(WorkflowRunModel)
            .options(selectinload(WorkflowRunModel.steps))
            .where(WorkflowRunModel.id == workflow_run_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise NotFoundError("WorkflowRun", workflow_run_id)

        notes = await self._linked_notes_for_workflow(row)
        daily_task_id = row.daily_task_id

        # Stop orchestrator loop ASAP.
        orch_task = _orchestrator_tasks.get(workflow_run_id)
        if orch_task and not orch_task.done():
            orch_task.cancel()

        run_svc = RunService(self.db)
        for step in row.steps:
            if step.agent_run_id:
                try:
                    await run_svc.cancel_run(step.agent_run_id)
                except Exception:
                    logger.info(
                        "cancel agent run %s skipped", step.agent_run_id, exc_info=True
                    )
            if step.status not in _TERMINAL:
                step.status = RunStatus.CANCELLED
                step.finished_at = datetime.now(timezone.utc)
                step.progress = 0

        if row.status not in _TERMINAL:
            row.status = RunStatus.CANCELLED
            row.finished_at = datetime.now(timezone.utc)
            row.error_message = row.error_message or "已由用户终止"

        deleted_notes = 0
        retained_notes = len(notes)
        if delete_notes and notes:
            from app.models.schedule import TaskNoteModel

            note_ids = [n.id for n in notes]
            to_delete = (
                await self.db.execute(
                    select(TaskNoteModel).where(TaskNoteModel.id.in_(note_ids))
                )
            ).scalars().all()
            for note in to_delete:
                await self.db.delete(note)
            deleted_notes = len(to_delete)
            retained_notes = 0

        record_deleted = False
        if delete_record:
            # agent_run.step_run_id FK blocks cascading delete of step_run — detach first.
            from app.models.run import AgentRunModel

            step_ids = [s.id for s in row.steps]
            if step_ids:
                await self.db.execute(
                    update(AgentRunModel)
                    .where(AgentRunModel.step_run_id.in_(step_ids))
                    .values(step_run_id=None)
                )
                await self.db.flush()

            await self.db.delete(row)
            record_deleted = True
            _orchestrator_tasks.pop(workflow_run_id, None)

        await self.db.flush()
        return WorkflowTerminateResult(
            workflow_run_id=workflow_run_id,
            status=RunStatus.CANCELLED,
            deleted_notes=deleted_notes,
            retained_notes=retained_notes,
            daily_task_id=daily_task_id,
            record_deleted=record_deleted,
        )

    async def get_run(self, workflow_run_id: str) -> WorkflowRunRead:
        result = await self.db.execute(
            select(WorkflowRunModel)
            .options(selectinload(WorkflowRunModel.steps))
            .where(WorkflowRunModel.id == workflow_run_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise NotFoundError("WorkflowRun", workflow_run_id)

        wf = await self.db.get(WorkflowDefinitionModel, row.workflow_id)
        step_defs_result = await self.db.execute(
            select(WorkflowStepDefModel)
            .where(WorkflowStepDefModel.workflow_id == row.workflow_id)
            .order_by(WorkflowStepDefModel.sort_order)
        )
        step_defs = list(step_defs_result.scalars().all())
        step_runs_by_key = {s.step_key: s for s in row.steps}

        agent_ids = {s.agent_id for s in row.steps}
        agents: dict[str, AgentModel] = {}
        if agent_ids:
            agent_rows = await self.db.execute(
                select(AgentModel)
                .options(joinedload(AgentModel.provider))
                .where(AgentModel.id.in_(agent_ids))
            )
            agents = {a.id: a for a in agent_rows.scalars().all()}

        steps_read: list[WorkflowStepRunRead] = []
        for step_def in step_defs:
            sr = step_runs_by_key.get(step_def.step_key)
            if not sr:
                continue
            agent = agents.get(sr.agent_id)
            steps_read.append(
                WorkflowStepRunRead(
                    step_key=sr.step_key,
                    label=step_def.label,
                    agent_id=sr.agent_id,
                    agent_name=agent.name if agent else None,
                    provider_name=agent.provider.name if agent and agent.provider else None,
                    depends_on=list(step_def.depends_on or []),
                    parallel=step_def.parallel,
                    status=sr.status,
                    progress=sr.progress,
                    agent_run_id=sr.agent_run_id,
                    summary=sr.summary or "",
                    started_at=sr.started_at,
                    finished_at=sr.finished_at,
                )
            )

        inp = row.input or {}
        note_count = await self._linked_note_count(row)
        return WorkflowRunRead(
            id=row.id,
            workflow_id=row.workflow_id,
            workflow_name=wf.name if wf else None,
            workflow_title=wf.title if wf else None,
            status=row.status,
            progress=row.progress,
            task_prompt=str(inp.get("task_prompt", "")),
            workspace_path=str(inp.get("workspace_path", "")),
            error_message=row.error_message,
            daily_task_id=row.daily_task_id,
            linked_note_count=note_count,
            steps=steps_read,
            started_at=row.started_at,
            finished_at=row.finished_at,
            created_at=row.created_at,
        )

    async def _execute_workflow(self, workflow_run_id: str) -> None:
        wf_run = await self.db.get(WorkflowRunModel, workflow_run_id)
        if not wf_run:
            return

        wf_run.status = RunStatus.RUNNING
        wf_run.started_at = datetime.now(timezone.utc)
        await self.db.commit()

        step_defs_result = await self.db.execute(
            select(WorkflowStepDefModel)
            .where(WorkflowStepDefModel.workflow_id == wf_run.workflow_id)
            .order_by(WorkflowStepDefModel.sort_order)
        )
        step_defs = list(step_defs_result.scalars().all())

        inp = wf_run.input or {}
        global_task = str(inp.get("task_prompt", ""))
        workspace_path = str(inp.get("workspace_path", ""))

        workflow_failed = False

        while True:
            await self.db.refresh(wf_run)
            if wf_run.status in _TERMINAL:
                break

            step_runs_result = await self.db.execute(
                select(StepRunModel)
                .where(StepRunModel.workflow_run_id == workflow_run_id)
                .execution_options(populate_existing=True)
            )
            step_runs = list(step_runs_result.scalars().all())
            status_by_key = {s.step_key: s.status for s in step_runs}

            if all(s == RunStatus.COMPLETED for s in status_by_key.values()):
                wf_run.status = RunStatus.COMPLETED
                wf_run.progress = 100
                wf_run.finished_at = datetime.now(timezone.utc)
                await self.db.commit()
                try:
                    from app.services.plan_progress_sync import sync_plan_items_from_workflow_run

                    await sync_plan_items_from_workflow_run(self.db, workflow_run_id, commit=True)
                except Exception:
                    logger.exception("plan progress sync failed on workflow complete")
                break

            if workflow_failed or any(s == RunStatus.FAILED for s in status_by_key.values()):
                if not any(s == RunStatus.RUNNING for s in status_by_key.values()):
                    wf_run.status = RunStatus.FAILED
                    wf_run.error_message = wf_run.error_message or "One or more steps failed"
                    wf_run.finished_at = datetime.now(timezone.utc)
                    await self.db.commit()
                    break

            ready = _ready_step_keys(step_defs, status_by_key)
            if not ready:
                if any(s == RunStatus.RUNNING for s in status_by_key.values()):
                    await asyncio.sleep(0.4)
                    continue
                if all(s == RunStatus.COMPLETED for s in status_by_key.values()):
                    wf_run.status = RunStatus.COMPLETED
                    wf_run.progress = 100
                    wf_run.finished_at = datetime.now(timezone.utc)
                    await self.db.commit()
                    break
                if workflow_failed:
                    wf_run.status = RunStatus.FAILED
                    wf_run.error_message = wf_run.error_message or "One or more steps failed"
                    wf_run.finished_at = datetime.now(timezone.utc)
                    await self.db.commit()
                    break
                wf_run.status = RunStatus.FAILED
                wf_run.error_message = "Workflow stalled: no runnable steps"
                wf_run.finished_at = datetime.now(timezone.utc)
                await self.db.commit()
                break

            results = await asyncio.gather(
                *[
                    _run_step_isolated(
                        workflow_run_id=workflow_run_id,
                        step_key=step.step_key,
                        global_task=global_task,
                        workspace_path=workspace_path,
                    )
                    for step in ready
                ],
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, Exception):
                    logger.exception("Step execution error in workflow %s", workflow_run_id)
                    workflow_failed = True
                elif result is False:
                    workflow_failed = True

            step_runs_result = await self.db.execute(
                select(StepRunModel)
                .where(StepRunModel.workflow_run_id == workflow_run_id)
                .execution_options(populate_existing=True)
            )
            step_runs = list(step_runs_result.scalars().all())
            completed = sum(1 for s in step_runs if s.status == RunStatus.COMPLETED)
            wf_run.progress = int(completed / max(len(step_defs), 1) * 100)
            await self.db.commit()

        logger.info("Workflow %s finished with status %s", workflow_run_id, wf_run.status)


async def _run_step_isolated(
    *,
    workflow_run_id: str,
    step_key: str,
    global_task: str,
    workspace_path: str,
) -> bool:
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        step_defs_result = await session.execute(
            select(WorkflowStepDefModel)
            .join(
                WorkflowRunModel,
                WorkflowStepDefModel.workflow_id == WorkflowRunModel.workflow_id,
            )
            .where(
                WorkflowRunModel.id == workflow_run_id,
                WorkflowStepDefModel.step_key == step_key,
            )
        )
        step_def = step_defs_result.scalar_one_or_none()
        if not step_def:
            return False

        step_run_result = await session.execute(
            select(StepRunModel).where(
                StepRunModel.workflow_run_id == workflow_run_id,
                StepRunModel.step_key == step_key,
            )
        )
        step_run = step_run_result.scalar_one_or_none()
        if not step_run or step_run.status != RunStatus.PENDING:
            return True

        step_run.status = RunStatus.RUNNING
        step_run.started_at = datetime.now(timezone.utc)
        step_run.progress = 10
        await session.commit()
        try:
            from app.services.plan_progress_sync import sync_plan_items_from_workflow_run

            await sync_plan_items_from_workflow_run(session, workflow_run_id, commit=True)
        except Exception:
            logger.exception("plan progress sync failed on step start %s", step_key)

        upstream: list[tuple[str, str, str]] = []
        dep_keys = list(step_def.depends_on or [])
        if dep_keys:
            dep_defs = {
                d.step_key: d
                for d in (
                    await session.execute(
                        select(WorkflowStepDefModel).where(
                            WorkflowStepDefModel.workflow_id == step_def.workflow_id,
                            WorkflowStepDefModel.step_key.in_(dep_keys),
                        )
                    )
                ).scalars().all()
            }
            dep_runs = (
                await session.execute(
                    select(StepRunModel).where(
                        StepRunModel.workflow_run_id == workflow_run_id,
                        StepRunModel.step_key.in_(dep_keys),
                        StepRunModel.status == RunStatus.COMPLETED,
                    )
                )
            ).scalars().all()
            for dep_run in dep_runs:
                dep_def = dep_defs.get(dep_run.step_key)
                label = dep_def.label if dep_def else dep_run.step_key
                upstream.append((dep_run.step_key, label, dep_run.summary or ""))

        reuse = await _workflow_reuses_same_agent_session(session, step_def.workflow_id)
        conversation_history = ""
        prior_run_ids: list[str] = []
        if reuse:
            prior_run_ids = await _prior_same_agent_run_ids(
                session,
                workflow_run_id=workflow_run_id,
                agent_id=step_def.agent_id,
                current_step_key=step_key,
            )
            if prior_run_ids:
                conversation_history = await _load_conversation_history(session, prior_run_ids)

        # When carrying same-agent history, drop redundant summaries from same-agent deps.
        if conversation_history and prior_run_ids:
            same_agent_keys = {
                s.step_key
                for s in (
                    await session.execute(
                        select(StepRunModel).where(
                            StepRunModel.workflow_run_id == workflow_run_id,
                            StepRunModel.agent_id == step_def.agent_id,
                            StepRunModel.status == RunStatus.COMPLETED,
                        )
                    )
                ).scalars().all()
            }
            upstream = [u for u in upstream if u[0] not in same_agent_keys]

        prompt = _build_step_prompt(
            global_task,
            step_def.label,
            step_def.step_key,
            upstream,
            conversation_history=conversation_history,
        )
        run_svc = RunService(session)
        agent_run = await run_svc.create_and_start(
            step_def.agent_id,
            prompt,
            step_run_id=step_run.id,
            workspace_path=workspace_path or None,
        )
        step_run.agent_run_id = agent_run.id
        await session.commit()
        agent_run_id = agent_run.id
        step_run_id = step_run.id

    final_status = await _wait_for_agent_run(agent_run_id)

    async with SessionLocal() as session2:
        sr = await session2.get(StepRunModel, step_run_id)
        if sr:
            sr.status = final_status
            sr.progress = 100 if final_status == RunStatus.COMPLETED else 0
            sr.finished_at = datetime.now(timezone.utc)
            if final_status == RunStatus.COMPLETED:
                sr.summary = await _extract_run_summary(session2, agent_run_id)
                try:
                    from app.services.task_note_sync import sync_markdown_notes_from_agent_run

                    await sync_markdown_notes_from_agent_run(session2, agent_run_id)
                except Exception:
                    logger.exception("markdown note sync failed after step %s", step_key)
            await session2.commit()
            try:
                from app.services.plan_progress_sync import sync_plan_items_from_workflow_run

                await sync_plan_items_from_workflow_run(session2, workflow_run_id, commit=True)
            except Exception:
                logger.exception("plan progress sync failed after step %s", step_key)
    return final_status == RunStatus.COMPLETED


async def _wait_for_agent_run(agent_run_id: str, poll_seconds: float = 0.4) -> str:
    from app.db.session import SessionLocal

    while True:
        async with SessionLocal() as session:
            row = await session.get(AgentRunModel, agent_run_id)
            if row and row.status in _TERMINAL:
                return row.status
        await asyncio.sleep(poll_seconds)


async def _orchestrate_workflow(workflow_run_id: str) -> None:
    from app.db.session import SessionLocal

    try:
        async with SessionLocal() as session:
            orch = OrchestratorService(session)
            await orch._execute_workflow(workflow_run_id)
    except Exception:
        logger.exception("Workflow orchestration failed: %s", workflow_run_id)
        try:
            async with SessionLocal() as session:
                row = await session.get(WorkflowRunModel, workflow_run_id)
                if row and row.status not in _TERMINAL:
                    row.status = RunStatus.FAILED
                    row.error_message = "Orchestrator internal error"
                    row.finished_at = datetime.now(timezone.utc)
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark workflow %s as failed", workflow_run_id)
    finally:
        _orchestrator_tasks.pop(workflow_run_id, None)
