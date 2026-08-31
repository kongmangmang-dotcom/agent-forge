from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.schemas.common import ListResponse
from app.schemas.workflow import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionRead,
    WorkflowDefinitionSummary,
    WorkflowDefinitionUpdate,
    WorkflowRunCreate,
    WorkflowRunRead,
    WorkflowRunSummary,
    WorkflowTerminatePreview,
    WorkflowTerminateRequest,
    WorkflowTerminateResult,
)
from app.services.orchestrator import OrchestratorService
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("/definitions", response_model=ListResponse[WorkflowDefinitionSummary])
async def list_definitions(db: AsyncSession = Depends(get_session)):
    items = await WorkflowService(db).list_definitions()
    return {"items": items}


@router.post("/definitions", response_model=WorkflowDefinitionRead, status_code=201)
async def create_definition(
    body: WorkflowDefinitionCreate, db: AsyncSession = Depends(get_session)
):
    return await WorkflowService(db).create_definition(body)


@router.get("/definitions/{definition_id}", response_model=WorkflowDefinitionRead)
async def get_definition(definition_id: str, db: AsyncSession = Depends(get_session)):
    return await WorkflowService(db).get_definition(definition_id)


@router.patch("/definitions/{definition_id}", response_model=WorkflowDefinitionRead)
async def update_definition(
    definition_id: str,
    body: WorkflowDefinitionUpdate,
    db: AsyncSession = Depends(get_session),
):
    return await WorkflowService(db).update_definition(definition_id, body)


@router.delete("/definitions/{definition_id}", status_code=204)
async def delete_definition(definition_id: str, db: AsyncSession = Depends(get_session)):
    await WorkflowService(db).delete_definition(definition_id)


@router.get("/runs", response_model=ListResponse[WorkflowRunSummary])
async def list_workflow_runs(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
):
    items = await OrchestratorService(db).list_runs(status=status)
    return {"items": items}


@router.post("/runs", response_model=WorkflowRunRead, status_code=201)
async def start_workflow_run(body: WorkflowRunCreate, db: AsyncSession = Depends(get_session)):
    row = await OrchestratorService(db).start_workflow(
        body.workflow_definition_id,
        body.task_prompt,
        body.workspace_path,
    )
    return await OrchestratorService(db).get_run(row.id)


@router.get("/runs/{workflow_run_id}", response_model=WorkflowRunRead)
async def get_workflow_run(workflow_run_id: str, db: AsyncSession = Depends(get_session)):
    return await OrchestratorService(db).get_run(workflow_run_id)


@router.get(
    "/runs/{workflow_run_id}/terminate-preview",
    response_model=WorkflowTerminatePreview,
)
async def terminate_workflow_preview(
    workflow_run_id: str, db: AsyncSession = Depends(get_session)
):
    return await OrchestratorService(db).terminate_preview(workflow_run_id)


@router.post(
    "/runs/{workflow_run_id}/terminate",
    response_model=WorkflowTerminateResult,
)
async def terminate_workflow_run(
    workflow_run_id: str,
    body: WorkflowTerminateRequest | None = None,
    db: AsyncSession = Depends(get_session),
):
    req = body or WorkflowTerminateRequest()
    return await OrchestratorService(db).terminate_workflow(
        workflow_run_id,
        delete_notes=req.delete_notes,
        delete_record=req.delete_record,
    )
