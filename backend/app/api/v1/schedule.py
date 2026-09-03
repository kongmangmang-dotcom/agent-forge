from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_session
from app.api.v1.runs import _run_read
from app.models.agent import AgentModel
from app.schemas.common import ListResponse
from app.schemas.run import RunRead
from app.schemas.schedule import (
    DailyTaskCreate,
    DailyTaskRead,
    DailyTaskSummary,
    DailyTaskUpdate,
    DayOverview,
    DayOverviewRange,
    PlanTodayRequest,
    PlanTodayResponse,
    RegeneratePlanRequest,
    ContinueTaskRequest,
    StartTaskWorkflowRequest,
    TaskAgentChatRequest,
    TaskAgentChatResponse,
    TaskMemoryCreate,
    TaskMemoryRead,
    TaskMemoryUpdate,
    TaskNoteCreate,
    TaskNoteListItem,
    TaskNoteRead,
    TaskNoteUpdate,
)
from app.schemas.workflow import WorkflowRunRead
from app.services.schedule_service import ScheduleService

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("/overview", response_model=DayOverview)
async def day_overview(
    plan_date: date | None = Query(None),
    db: AsyncSession = Depends(get_session),
):
    return await ScheduleService(db).day_overview(plan_date=plan_date)


@router.get("/overview-range", response_model=DayOverviewRange)
async def day_overview_range(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    days: int = Query(14, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
):
    return await ScheduleService(db).day_overview_range(
        start_date=start_date,
        end_date=end_date,
        days=days,
    )


@router.get("/tasks", response_model=ListResponse[DailyTaskSummary])
async def list_tasks(
    plan_date: date | None = Query(None),
    db: AsyncSession = Depends(get_session),
):
    items = await ScheduleService(db).list_tasks(plan_date=plan_date)
    return {"items": items}


@router.get("/notes", response_model=ListResponse[TaskNoteListItem])
async def list_notes(
    plan_date: date | None = Query(None),
    days: int | None = Query(None, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
):
    """List notes/documents from schedule tasks (for knowledge base ingest)."""
    items = await ScheduleService(db).list_notes(plan_date=plan_date, days=days)
    return {"items": items}


@router.post("/tasks", response_model=DailyTaskRead, status_code=201)
async def create_task(body: DailyTaskCreate, db: AsyncSession = Depends(get_session)):
    return await ScheduleService(db).create_task(body)


@router.post("/tasks/plan-today", response_model=PlanTodayResponse)
async def plan_today(body: PlanTodayRequest, db: AsyncSession = Depends(get_session)):
    task = await ScheduleService(db).plan_today(
        body.goal,
        plan_date=body.plan_date,
        workflow_definition_id=body.workflow_definition_id,
    )
    return PlanTodayResponse(task=task)


@router.get("/tasks/{task_id}", response_model=DailyTaskRead)
async def get_task(task_id: str, db: AsyncSession = Depends(get_session)):
    return await ScheduleService(db).get_task(task_id)


@router.patch("/tasks/{task_id}", response_model=DailyTaskRead)
async def update_task(
    task_id: str, body: DailyTaskUpdate, db: AsyncSession = Depends(get_session)
):
    return await ScheduleService(db).update_task(task_id, body)


@router.post("/tasks/{task_id}/continue", response_model=DailyTaskRead, status_code=201)
async def continue_task(
    task_id: str,
    body: ContinueTaskRequest | None = None,
    db: AsyncSession = Depends(get_session),
):
    return await ScheduleService(db).continue_task(
        task_id,
        target_date=body.target_date if body else None,
    )


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_session)):
    await ScheduleService(db).delete_task(task_id)
    return Response(status_code=204)


@router.post("/tasks/{task_id}/regenerate-plan", response_model=DailyTaskRead)
async def regenerate_plan(
    task_id: str,
    body: RegeneratePlanRequest | None = None,
    db: AsyncSession = Depends(get_session),
):
    wf_id = body.workflow_definition_id if body else None
    return await ScheduleService(db).regenerate_plan(task_id, workflow_definition_id=wf_id)


@router.post("/tasks/{task_id}/start-workflow", response_model=WorkflowRunRead)
async def start_task_workflow(
    task_id: str,
    body: StartTaskWorkflowRequest | None = None,
    db: AsyncSession = Depends(get_session),
):
    return await ScheduleService(db).start_task_workflow(
        task_id,
        task_prompt=body.task_prompt if body else None,
        workflow_definition_id=body.workflow_definition_id if body else None,
    )


@router.post("/tasks/{task_id}/agent-chat", response_model=TaskAgentChatResponse)
async def task_agent_chat(
    task_id: str,
    body: TaskAgentChatRequest,
    db: AsyncSession = Depends(get_session),
):
    return await ScheduleService(db).agent_chat(
        task_id,
        agent_id=body.agent_id,
        message=body.message,
        run_id=body.run_id,
        new_session=body.new_session,
    )


@router.get("/tasks/{task_id}/agent-chat/latest", response_model=RunRead | None)
async def latest_task_agent_chat(
    task_id: str,
    agent_id: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
):
    row = await ScheduleService(db).get_latest_agent_chat_run(task_id, agent_id=agent_id)
    if not row:
        return None
    result = await db.execute(
        select(AgentModel)
        .options(joinedload(AgentModel.provider))
        .where(AgentModel.id == row.agent_id)
    )
    agent = result.scalar_one_or_none()
    return _run_read(row, agent)


@router.post("/tasks/{task_id}/notes", response_model=TaskNoteRead, status_code=201)
async def create_note(
    task_id: str, body: TaskNoteCreate, db: AsyncSession = Depends(get_session)
):
    return await ScheduleService(db).create_note(task_id, body)


@router.patch("/tasks/{task_id}/notes/{note_id}", response_model=TaskNoteRead)
async def update_note(
    task_id: str,
    note_id: str,
    body: TaskNoteUpdate,
    db: AsyncSession = Depends(get_session),
):
    return await ScheduleService(db).update_note(task_id, note_id, body)


@router.delete("/tasks/{task_id}/notes/{note_id}", status_code=204)
async def delete_note(
    task_id: str, note_id: str, db: AsyncSession = Depends(get_session)
):
    await ScheduleService(db).delete_note(task_id, note_id)
    return Response(status_code=204)


@router.get("/tasks/{task_id}/notes/{note_id}/download")
async def download_note(
    task_id: str, note_id: str, db: AsyncSession = Depends(get_session)
):
    from urllib.parse import quote

    from fastapi.responses import Response as FastAPIResponse

    filename, content, media_type = await ScheduleService(db).get_note_download(
        task_id, note_id
    )
    # RFC 5987 filename* for non-ASCII titles
    disposition = (
        f"attachment; filename=\"{filename.encode('ascii', 'replace').decode('ascii')}\"; "
        f"filename*=UTF-8''{quote(filename)}"
    )
    return FastAPIResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


@router.post("/tasks/{task_id}/memories", response_model=TaskMemoryRead, status_code=201)
async def create_memory(
    task_id: str, body: TaskMemoryCreate, db: AsyncSession = Depends(get_session)
):
    return await ScheduleService(db).create_memory(task_id, body)


@router.patch("/tasks/{task_id}/memories/{memory_id}", response_model=TaskMemoryRead)
async def update_memory(
    task_id: str,
    memory_id: str,
    body: TaskMemoryUpdate,
    db: AsyncSession = Depends(get_session),
):
    return await ScheduleService(db).update_memory(task_id, memory_id, body)


@router.delete("/tasks/{task_id}/memories/{memory_id}", status_code=204)
async def delete_memory(
    task_id: str, memory_id: str, db: AsyncSession = Depends(get_session)
):
    await ScheduleService(db).delete_memory(task_id, memory_id)
    return Response(status_code=204)
