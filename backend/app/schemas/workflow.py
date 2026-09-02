from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class WorkflowStepDefCreate(BaseModel):
    step_key: str
    label: str
    agent_id: str
    role: str = ""
    depends_on: list[str] = Field(default_factory=list)
    parallel: bool = False
    sort_order: int = 0


class WorkflowDefinitionCreate(BaseModel):
    name: str
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStepDefCreate] = Field(default_factory=list)


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = None
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    options: dict[str, Any] | None = None
    steps: list[WorkflowStepDefCreate] | None = None


class WorkflowStepDefRead(ORMModel):
    id: str
    step_key: str
    label: str
    agent_id: str
    agent_name: str | None = None
    role: str = ""
    depends_on: list[str]
    parallel: bool
    sort_order: int


class WorkflowDefinitionRead(ORMModel):
    id: str
    name: str
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    options: dict[str, Any]
    created_at: datetime
    steps: list[WorkflowStepDefRead] = Field(default_factory=list)


class WorkflowDefinitionSummary(ORMModel):
    id: str
    name: str
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    step_count: int = 0
    created_at: datetime


class WorkflowRunCreate(BaseModel):
    workflow_definition_id: str
    task_prompt: str = Field(min_length=1)
    workspace_path: str = ""


class WorkflowStepRunRead(ORMModel):
    step_key: str
    label: str
    agent_id: str
    agent_name: str | None = None
    provider_name: str | None = None
    role: str = ""
    depends_on: list[str] = Field(default_factory=list)
    parallel: bool = False
    status: str
    progress: int = 0
    agent_run_id: str | None = None
    summary: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None


class WorkflowRunRead(ORMModel):
    id: str
    workflow_id: str
    workflow_name: str | None = None
    workflow_title: str | None = None
    status: str
    progress: int
    task_prompt: str
    workspace_path: str
    error_message: str | None = None
    daily_task_id: str | None = None
    linked_note_count: int = 0
    steps: list[WorkflowStepRunRead] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class WorkflowRunSummary(ORMModel):
    id: str
    workflow_id: str
    workflow_title: str | None = None
    status: str
    progress: int
    task_prompt: str
    daily_task_id: str | None = None
    linked_note_count: int = 0
    started_at: datetime | None = None
    created_at: datetime


class WorkflowTerminateRequest(BaseModel):
    """Terminate (cancel) a workflow run; optionally delete linked task notes."""

    delete_notes: bool = False
    delete_record: bool = True


class WorkflowLinkedNote(BaseModel):
    id: str
    title: str
    file_path: str = ""


class WorkflowTerminatePreview(BaseModel):
    workflow_run_id: str
    daily_task_id: str | None = None
    status: str
    note_count: int = 0
    notes: list[WorkflowLinkedNote] = Field(default_factory=list)


class WorkflowTerminateResult(BaseModel):
    workflow_run_id: str
    status: str
    deleted_notes: int = 0
    retained_notes: int = 0
    daily_task_id: str | None = None
    record_deleted: bool = False
