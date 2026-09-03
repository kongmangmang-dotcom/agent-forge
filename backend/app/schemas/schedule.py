from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class TaskPlanItemRead(ORMModel):
    id: str
    title: str
    detail: str = ""
    scheduled_time: str | None = None
    status: str
    agent_id: str | None = None
    agent_name: str | None = None
    linked_step_key: str | None = None
    workflow_definition_id: str | None = None
    sort_order: int = 0


class WorkflowPlanGroup(ORMModel):
    workflow_definition_id: str
    workflow_name: str | None = None
    workflow_title: str | None = None
    is_active: bool = False
    latest_run_id: str | None = None
    active_run_id: str | None = None
    plan_item_count: int = 0
    plan_done_count: int = 0
    plan_items: list[TaskPlanItemRead] = Field(default_factory=list)

class TaskNoteCreate(BaseModel):
    kind: str = "markdown"
    title: str = ""
    body: str = ""
    file_path: str = ""


class TaskNoteUpdate(BaseModel):
    kind: str | None = None
    title: str | None = None
    body: str | None = None
    file_path: str | None = None


class TaskNoteRead(ORMModel):
    id: str
    daily_task_id: str
    kind: str
    title: str
    body: str
    file_path: str
    created_at: datetime
    updated_at: datetime


class TaskNoteListItem(ORMModel):
    id: str
    daily_task_id: str
    task_title: str
    plan_date: date
    kind: str
    title: str
    body_preview: str = ""
    file_path: str = ""
    has_content: bool = False
    created_at: datetime
    updated_at: datetime


class TaskMemoryCreate(BaseModel):
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False


class TaskMemoryUpdate(BaseModel):
    content: str | None = None
    tags: list[str] | None = None
    pinned: bool | None = None


class TaskMemoryRead(ORMModel):
    id: str
    daily_task_id: str
    content: str
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False
    created_at: datetime
    updated_at: datetime


class DailyTaskCreate(BaseModel):
    title: str = Field(min_length=1)
    type: str = "normal"
    priority: str = "medium"
    summary: str = ""
    requirement: str = ""
    plan_date: date | None = None
    workflow_definition_id: str | None = None
    with_plan: bool = False


class DailyTaskUpdate(BaseModel):
    title: str | None = None
    type: str | None = None
    status: str | None = None
    priority: str | None = None
    summary: str | None = None
    requirement: str | None = None
    workflow_definition_id: str | None = None
    bound_workflow_ids: list[str] | None = None


class ContinueTaskRequest(BaseModel):
    target_date: date | None = None


class DailyTaskRead(ORMModel):
    id: str
    plan_date: date
    title: str
    type: str
    status: str
    priority: str
    summary: str
    requirement: str = ""
    workflow_definition_id: str | None = None
    bound_workflow_ids: list[str] = Field(default_factory=list)
    workflow_name: str | None = None
    workflow_title: str | None = None
    active_workflow_run_id: str | None = None
    latest_workflow_run_id: str | None = None
    plan_author: str | None = None
    plan_updated_at: datetime | None = None
    continued_from_id: str | None = None
    continued_to_id: str | None = None
    continued_from_plan_date: date | None = None
    continued_from_title: str | None = None
    continued_to_plan_date: date | None = None
    continued_to_title: str | None = None
    created_at: datetime
    updated_at: datetime
    plan_items: list[TaskPlanItemRead] = Field(default_factory=list)
    workflow_plans: list[WorkflowPlanGroup] = Field(default_factory=list)
    notes: list[TaskNoteRead] = Field(default_factory=list)
    memories: list[TaskMemoryRead] = Field(default_factory=list)


class DailyTaskSummary(ORMModel):
    id: str
    plan_date: date
    title: str
    type: str
    status: str
    priority: str
    summary: str
    requirement: str = ""
    workflow_definition_id: str | None = None
    bound_workflow_ids: list[str] = Field(default_factory=list)
    workflow_name: str | None = None
    workflow_title: str | None = None
    plan_item_count: int = 0
    plan_done_count: int = 0
    plan_author: str | None = None
    plan_updated_at: datetime | None = None
    continued_from_id: str | None = None
    continued_to_id: str | None = None
    continued_from_plan_date: date | None = None
    continued_to_plan_date: date | None = None
    created_at: datetime

class DayOverview(BaseModel):
    plan_date: date
    task_count: int = 0
    todo_count: int = 0
    in_progress_count: int = 0
    done_count: int = 0
    plan_item_count: int = 0
    plan_done_count: int = 0


class DayOverviewRange(BaseModel):
    start_date: date
    end_date: date
    days: list[DayOverview] = Field(default_factory=list)
    total_task_count: int = 0
    total_done_count: int = 0
    total_plan_item_count: int = 0
    total_plan_done_count: int = 0


class PlanTodayRequest(BaseModel):
    goal: str = Field(min_length=1)
    workflow_definition_id: str | None = None
    auto_start_dev_workflows: bool = False
    plan_date: date | None = None


class RegeneratePlanRequest(BaseModel):
    workflow_definition_id: str | None = None


class StartTaskWorkflowRequest(BaseModel):
    task_prompt: str | None = None
    workflow_definition_id: str | None = None


class TaskAgentChatRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    run_id: str | None = None
    new_session: bool = False


class TaskAgentChatResponse(BaseModel):
    run_id: str
    agent_id: str
    status: str
    created: bool
    mode: str  # start | inject | continue
    docs_attached: bool = False


class PlanTodayResponse(BaseModel):
    task: DailyTaskRead


class DailyReportResponse(BaseModel):
    plan_date: str
    knowledge_id: str
    knowledge_name: str
    document_id: str | None = None
    document_name: str | None = None
    skipped: bool = False
    reason: str | None = None
    task_count: int = 0
    chat_backend: str = ""
