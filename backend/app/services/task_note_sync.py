"""Sync markdown artifacts from AgentRun file changes into DailyTask notes."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.models.run import AgentRunModel, FileChangeModel
from app.models.schedule import TaskNoteModel
from app.models.workflow import StepRunModel, WorkflowRunModel

logger = logging.getLogger(__name__)

_MD_SUFFIXES = (".md", ".markdown", ".mdx")
_BODY_MAX = 120_000


def _is_markdown_path(path: str) -> bool:
    lower = path.strip().lower().replace("\\", "/")
    return any(lower.endswith(suf) for suf in _MD_SUFFIXES)


def _normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def _title_from_path(path: str) -> str:
    name = Path(_normalize_path(path)).name
    return name or path


def _resolve_abs_path(workspace: str, rel_or_abs: str) -> Path:
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p
    root = Path(workspace or ".")
    return (root / p).resolve()


def _read_markdown_body(workspace: str, path: str) -> str:
    try:
        abs_path = _resolve_abs_path(workspace, path)
        if not abs_path.is_file():
            return ""
        text = abs_path.read_text(encoding="utf-8", errors="replace")
        if len(text) > _BODY_MAX:
            return text[:_BODY_MAX] + "\n\n…(已截断)"
        return text
    except Exception:
        logger.debug("failed reading markdown %s", path, exc_info=True)
        return ""


async def resolve_daily_task_id(session: AsyncSession, agent_run: AgentRunModel) -> str | None:
    if not agent_run.step_run_id:
        return None
    step = await session.get(StepRunModel, agent_run.step_run_id)
    if not step:
        return None
    wf_run = await session.get(WorkflowRunModel, step.workflow_run_id)
    if not wf_run:
        return None
    return wf_run.daily_task_id


async def _upsert_note(
    session: AsyncSession,
    *,
    daily_task_id: str,
    file_path: str,
    body: str,
    source_run_id: str,
) -> TaskNoteModel:
    path = _normalize_path(file_path)
    result = await session.execute(
        select(TaskNoteModel).where(
            TaskNoteModel.daily_task_id == daily_task_id,
            TaskNoteModel.file_path == path,
        )
    )
    existing = result.scalar_one_or_none()
    title = _title_from_path(path)
    kind = "markdown" if body.strip() else "file"
    suffix = f"\n\n---\n来源 Agent Run: `{source_run_id}`"
    stored_body = (body.strip() + suffix) if body.strip() else f"（文件路径登记）{suffix}"

    if existing:
        existing.title = title or existing.title
        existing.kind = kind
        existing.body = stored_body
        existing.file_path = path
        await session.flush()
        return existing

    note = TaskNoteModel(
        id=new_id("tn"),
        daily_task_id=daily_task_id,
        kind=kind,
        title=title,
        body=stored_body,
        file_path=path,
    )
    session.add(note)
    await session.flush()
    return note


async def collect_markdown_paths(
    session: AsyncSession,
    agent_run: AgentRunModel,
) -> list[str]:
    result = await session.execute(
        select(FileChangeModel)
        .where(FileChangeModel.run_id == agent_run.id)
        .order_by(FileChangeModel.created_at.asc())
    )
    paths: list[str] = []
    seen: set[str] = set()
    for row in result.scalars().all():
        if row.action == "deleted":
            continue
        if not _is_markdown_path(row.path or ""):
            continue
        key = _normalize_path(row.path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(key)

    # Fallback: scan workspace for .md touched during/after the run start.
    workspace = (agent_run.workspace_path or "").strip()
    if workspace and agent_run.started_at:
        root = Path(workspace)
        if root.is_dir():
            start_ts = agent_run.started_at.timestamp()
            end_ts = (
                agent_run.finished_at.timestamp() + 5
                if agent_run.finished_at
                else start_ts + 3600
            )
            try:
                for p in root.rglob("*"):
                    if not p.is_file() or not _is_markdown_path(str(p)):
                        continue
                    try:
                        mtime = p.stat().st_mtime
                    except OSError:
                        continue
                    if mtime < start_ts or mtime > end_ts:
                        continue
                    try:
                        rel = str(p.relative_to(root)).replace("\\", "/")
                    except ValueError:
                        rel = str(p).replace("\\", "/")
                    if rel not in seen:
                        seen.add(rel)
                        paths.append(rel)
            except Exception:
                logger.debug("workspace md scan failed for %s", workspace, exc_info=True)

    return paths


async def sync_markdown_notes_from_agent_run(
    session: AsyncSession,
    agent_run_id: str,
) -> int:
    """Create/update task notes for markdown files produced by an agent run.

    Returns number of notes upserted. No-op if run is not linked to a daily task.
    """
    agent_run = await session.get(AgentRunModel, agent_run_id)
    if not agent_run:
        return 0

    daily_task_id = await resolve_daily_task_id(session, agent_run)
    if not daily_task_id:
        return 0

    paths = await collect_markdown_paths(session, agent_run)
    if not paths:
        return 0

    count = 0
    for path in paths:
        body = _read_markdown_body(agent_run.workspace_path or ".", path)
        await _upsert_note(
            session,
            daily_task_id=daily_task_id,
            file_path=path,
            body=body,
            source_run_id=agent_run_id,
        )
        count += 1

    logger.info(
        "synced %s markdown note(s) to task %s from run %s",
        count,
        daily_task_id,
        agent_run_id,
    )
    return count
