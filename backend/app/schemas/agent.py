from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AgentPermissions(BaseModel):
    read_files: bool = True
    write_files: bool = False
    run_commands: bool = False
    run_tests: bool = False
    network: bool = False


class AgentLimits(BaseModel):
    timeout_minutes: int = 30
    max_rounds: int = 3


class AgentCreate(BaseModel):
    name: str
    provider_id: str
    model: str = ""
    role: str
    system_prompt: str = ""
    workspace_path: str = ""
    permissions: AgentPermissions = Field(default_factory=AgentPermissions)
    limits: AgentLimits = Field(default_factory=AgentLimits)
    streaming: bool = True


class AgentUpdate(BaseModel):
    name: str | None = None
    provider_id: str | None = None
    model: str | None = None
    role: str | None = None
    system_prompt: str | None = None
    workspace_path: str | None = None
    permissions: AgentPermissions | None = None
    limits: AgentLimits | None = None
    streaming: bool | None = None


class AgentRead(ORMModel):
    id: str
    name: str
    provider_id: str
    provider_name: str | None = None
    model: str
    role: str
    system_prompt: str
    workspace_path: str
    permissions: dict[str, Any]
    limits: dict[str, Any]
    streaming: bool
    created_at: datetime
    updated_at: datetime


class RoleTemplate(BaseModel):
    role: str
    label: str
    desc: str
    default_provider_kind: str
