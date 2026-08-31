from datetime import datetime
from typing import Any, AsyncIterator, Protocol

from pydantic import BaseModel, Field

from app.domain.enums import EventType, ProviderType, RunStatus


class AgentPermissions(BaseModel):
    read_files: bool = True
    write_files: bool = False
    run_commands: bool = False
    run_tests: bool = False
    network: bool = False


class AgentLimits(BaseModel):
    timeout_minutes: int = 30
    max_rounds: int = 3


class ProviderConfig(BaseModel):
    id: str
    kind: str
    type: ProviderType
    endpoint: str = ""
    default_model: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    id: str
    name: str
    provider_id: str
    model: str
    role: str
    system_prompt: str = ""
    workspace_path: str = ""
    permissions: AgentPermissions = Field(default_factory=AgentPermissions)
    limits: AgentLimits = Field(default_factory=AgentLimits)
    streaming: bool = True


class SessionHandle(BaseModel):
    run_id: str
    provider_kind: str
    external_session_id: str | None = None


class TaskPayload(BaseModel):
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentEvent(BaseModel):
    run_id: str
    agent_id: str
    type: EventType | str
    status: RunStatus | str = RunStatus.RUNNING
    content: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    workflow_run_id: str | None = None
    step_id: str | None = None


class FileChange(BaseModel):
    path: str
    action: str
    lines_summary: str = ""
    diff: str | None = None


class ConnectionResult(BaseModel):
    ok: bool
    message: str = ""


class AgentProvider(Protocol):
    """统一 Provider 接口 — 所有 OpenAI/Codex/Cursor 适配器实现此协议。"""

    provider_kind: str

    async def test_connection(self, config: ProviderConfig) -> ConnectionResult: ...

    async def create_session(self, agent: AgentConfig, run_id: str) -> SessionHandle: ...

    async def send_task(self, session: SessionHandle, task: TaskPayload) -> None: ...

    async def inject_message(self, session: SessionHandle, content: str) -> None: ...

    async def stream_events(self, session: SessionHandle) -> AsyncIterator[AgentEvent]: ...

    async def pause(self, session: SessionHandle) -> None: ...

    async def resume(self, session: SessionHandle) -> None: ...

    async def cancel(self, session: SessionHandle) -> None: ...

    async def collect_file_changes(self, session: SessionHandle) -> list[FileChange]: ...
