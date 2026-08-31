from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class CreateRunRequest(BaseModel):
    agent_id: str
    task_prompt: str = Field(min_length=1)


class RunRead(ORMModel):
    id: str
    agent_id: str
    agent_name: str | None = None
    provider_kind: str | None = None
    provider_name: str | None = None
    status: str
    task_prompt: str
    workspace_path: str
    tokens_used: int
    command_output: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class MessageRead(ORMModel):
    id: str
    run_id: str
    role: str
    content: str
    streaming: bool
    created_at: datetime


class EventRead(ORMModel):
    id: int
    run_id: str
    type: str
    status: str
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class FileChangeRead(ORMModel):
    id: int
    run_id: str
    path: str
    action: str
    lines_summary: str
    diff: str | None
    created_at: datetime


class InjectMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    interrupt_current: bool = True
