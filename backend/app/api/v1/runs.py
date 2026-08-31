import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_session
from app.models.agent import AgentModel
from app.models.run import AgentEventModel, AgentMessageModel, AgentRunModel, FileChangeModel
from app.schemas.common import ListResponse
from app.schemas.run import (
    CreateRunRequest,
    EventRead,
    FileChangeRead,
    InjectMessageRequest,
    MessageRead,
    RunRead,
)
from app.services.event_bus import event_bus
from app.services.run_service import RunService

router = APIRouter(prefix="/runs", tags=["runs"])


def _run_read(row: AgentRunModel, agent: AgentModel | None = None) -> RunRead:
    provider = agent.provider if agent else None
    return RunRead(
        id=row.id,
        agent_id=row.agent_id,
        agent_name=agent.name if agent else None,
        provider_kind=provider.kind if provider else None,
        provider_name=provider.name if provider else None,
        status=row.status,
        task_prompt=row.task_prompt,
        workspace_path=row.workspace_path,
        tokens_used=row.tokens_used,
        command_output=row.command_output,
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
    )


@router.get("", response_model=ListResponse[RunRead])
async def list_runs(status: str | None = None, db: AsyncSession = Depends(get_session)):
    svc = RunService(db)
    rows = await svc.list_runs(status=status)
    agent_ids = {r.agent_id for r in rows}
    agents: dict[str, AgentModel] = {}
    if agent_ids:
        result = await db.execute(
            select(AgentModel)
            .options(joinedload(AgentModel.provider))
            .where(AgentModel.id.in_(agent_ids))
        )
        for a in result.scalars().unique().all():
            agents[a.id] = a
    return {"items": [_run_read(r, agents.get(r.agent_id)) for r in rows]}


@router.post("", response_model=RunRead, status_code=201)
async def create_run(body: CreateRunRequest, db: AsyncSession = Depends(get_session)):
    svc = RunService(db)
    row = await svc.create_and_start(body.agent_id, body.task_prompt)
    agent = await db.get(AgentModel, row.agent_id)
    if agent:
        await db.refresh(agent, ["provider"])
    return _run_read(row, agent)


@router.get("/{run_id}", response_model=RunRead)
async def get_run(run_id: str, db: AsyncSession = Depends(get_session)):
    svc = RunService(db)
    row = await svc.get_run(run_id)
    result = await db.execute(
        select(AgentModel).options(joinedload(AgentModel.provider)).where(AgentModel.id == row.agent_id)
    )
    agent = result.scalar_one_or_none()
    return _run_read(row, agent)


@router.get("/{run_id}/messages", response_model=ListResponse[MessageRead])
async def get_messages(run_id: str, db: AsyncSession = Depends(get_session)):
    await RunService(db).get_run(run_id)
    result = await db.execute(
        select(AgentMessageModel)
        .where(AgentMessageModel.run_id == run_id)
        .order_by(AgentMessageModel.created_at)
    )
    items = [
        MessageRead(
            id=m.id,
            run_id=m.run_id,
            role=m.role,
            content=m.content,
            streaming=m.streaming,
            created_at=m.created_at,
        )
        for m in result.scalars().all()
    ]
    return {"items": items}


@router.get("/{run_id}/events", response_model=ListResponse[EventRead])
async def get_events(run_id: str, db: AsyncSession = Depends(get_session)):
    await RunService(db).get_run(run_id)
    result = await db.execute(
        select(AgentEventModel).where(AgentEventModel.run_id == run_id).order_by(AgentEventModel.created_at)
    )
    items = [
        EventRead(
            id=e.id,
            run_id=e.run_id,
            type=e.type,
            status=e.status,
            content=e.content,
            metadata=e.metadata_ or {},
            created_at=e.created_at,
        )
        for e in result.scalars().all()
    ]
    return {"items": items}


@router.get("/{run_id}/files", response_model=ListResponse[FileChangeRead])
async def get_files(run_id: str, db: AsyncSession = Depends(get_session)):
    await RunService(db).get_run(run_id)
    result = await db.execute(
        select(FileChangeModel).where(FileChangeModel.run_id == run_id).order_by(FileChangeModel.created_at)
    )
    items = [
        FileChangeRead(
            id=f.id,
            run_id=f.run_id,
            path=f.path,
            action=f.action,
            lines_summary=f.lines_summary,
            diff=f.diff,
            created_at=f.created_at,
        )
        for f in result.scalars().all()
    ]
    return {"items": items}


@router.post("/{run_id}/messages", status_code=202)
async def inject_message(run_id: str, body: InjectMessageRequest, db: AsyncSession = Depends(get_session)):
    await RunService(db).inject_message(run_id, body.content)
    return {"run_id": run_id, "accepted": True, "content": body.content}


@router.post("/{run_id}/cancel", response_model=RunRead)
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_session)):
    svc = RunService(db)
    row = await svc.cancel_run(run_id)
    result = await db.execute(
        select(AgentModel).options(joinedload(AgentModel.provider)).where(AgentModel.id == row.agent_id)
    )
    agent = result.scalar_one_or_none()
    return _run_read(row, agent)


@router.post("/{run_id}/pause")
async def pause_run(run_id: str):
    return {"run_id": run_id, "status": "paused", "message": "Pause not yet implemented for CLI providers"}


@router.post("/{run_id}/resume")
async def resume_run(run_id: str):
    return {"run_id": run_id, "status": "running", "message": "Resume not yet implemented"}


@router.post("/{run_id}/approve")
async def approve_run(run_id: str):
    return {"run_id": run_id, "status": "approved", "message": "Not implemented"}
