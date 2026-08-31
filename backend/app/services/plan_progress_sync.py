"""Sync DailyTask plan_items (and task status) from WorkflowRun StepRun progress."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.enums import RunStatus
from app.models.schedule import DailyTaskModel
from app.models.workflow import StepRunModel, WorkflowRunModel

logger = logging.getLogger(__name__)

_TERMINAL = {
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}


def step_status_to_plan(status: str) -> str:
    if status == RunStatus.COMPLETED:
        return "done"
    if status in (RunStatus.RUNNING, RunStatus.WAITING_APPROVAL, RunStatus.PAUSED):
        return "in_progress"
    return "todo"


async def sync_plan_items_from_workflow_run(
    session: AsyncSession,
    workflow_run_id: str,
    *,
    commit: bool = False,
) -> None:
    """Map StepRun statuses onto plan_items for the matching workflow template only."""
    wf = await session.get(WorkflowRunModel, workflow_run_id)
    if not wf or not wf.daily_task_id:
        return

    task = (
        await session.execute(
            select(DailyTaskModel)
            .options(selectinload(DailyTaskModel.plan_items))
            .where(DailyTaskModel.id == wf.daily_task_id)
        )
    ).scalar_one_or_none()
    if not task or not task.plan_items:
        return

    steps = (
        await session.execute(
            select(StepRunModel).where(StepRunModel.workflow_run_id == workflow_run_id)
        )
    ).scalars().all()
    by_key = {s.step_key: s.status for s in steps}

    changed = False
    matched_items = []
    for item in task.plan_items:
        item_wf = item.workflow_definition_id or task.workflow_definition_id
        if item_wf and item_wf != wf.workflow_id:
            continue
        key = (item.linked_step_key or "").strip()
        if not key or key not in by_key:
            continue
        matched_items.append(item)
        next_status = step_status_to_plan(by_key[key])
        if item.status != next_status:
            item.status = next_status
            changed = True
        if not item.workflow_definition_id:
            item.workflow_definition_id = wf.workflow_id
            changed = True

    if matched_items and wf.status == RunStatus.COMPLETED:
        if all(i.status == "done" for i in matched_items) and task.status != "done":
            # Only mark task done when every bound plan is fully done.
            all_items = list(task.plan_items)
            if all_items and all(i.status == "done" for i in all_items):
                task.status = "done"
                changed = True
    elif wf.status == RunStatus.RUNNING and task.status == "todo":
        task.status = "in_progress"
        changed = True

    if changed:
        task.updated_at = datetime.now(timezone.utc)
        await session.flush()
        if commit:
            await session.commit()


async def sync_plan_items_for_daily_task(
    session: AsyncSession,
    daily_task_id: str,
    *,
    commit: bool = False,
) -> str | None:
    """Sync from the latest run of each workflow template linked to this task."""
    runs = (
        await session.execute(
            select(WorkflowRunModel)
            .where(WorkflowRunModel.daily_task_id == daily_task_id)
            .order_by(WorkflowRunModel.created_at.desc())
        )
    ).scalars().all()
    if not runs:
        return None

    seen_wf: set[str] = set()
    latest_id: str | None = runs[0].id if runs else None
    for run in runs:
        if run.workflow_id in seen_wf:
            continue
        seen_wf.add(run.workflow_id)
        await sync_plan_items_from_workflow_run(session, run.id, commit=False)

    if commit:
        await session.commit()
    return latest_id


async def find_active_run_for_task(
    session: AsyncSession, daily_task_id: str
) -> WorkflowRunModel | None:
    return (
        await session.execute(
            select(WorkflowRunModel)
            .where(
                WorkflowRunModel.daily_task_id == daily_task_id,
                WorkflowRunModel.status.notin_(list(_TERMINAL)),
            )
            .order_by(WorkflowRunModel.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
