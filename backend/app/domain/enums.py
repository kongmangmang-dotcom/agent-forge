from enum import StrEnum


class ProviderType(StrEnum):
    MODEL_API = "model_api"
    CODING_AGENT = "coding_agent"
    LOCAL_RUNTIME = "local_runtime"


class ProviderKind(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    CODEX_CLI = "codex_cli"
    OPENCODE_CLI = "opencode_cli"
    CURSOR_CLI = "cursor_cli"
    DEMO_CLI = "demo_cli"


class AgentRole(StrEnum):
    PLANNER = "planner"
    RESEARCHER = "researcher"
    DEVELOPER = "developer"
    TESTER = "tester"
    REVIEWER = "reviewer"
    INTEGRATOR = "integrator"
    GAME_DESIGNER = "game_designer"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting_approval"


class EventType(StrEnum):
    SESSION_CREATED = "session_created"
    TASK_STARTED = "task_started"
    ASSISTANT_MESSAGE = "assistant_message"
    THINKING_UPDATE = "thinking_update"
    TOOL_CALL = "tool_call"
    COMMAND_STARTED = "command_started"
    COMMAND_FINISHED = "command_finished"
    FILE_CHANGED = "file_changed"
    TEST_STARTED = "test_started"
    TEST_FINISHED = "test_finished"
    APPROVAL_REQUIRED = "approval_required"
    AGENT_WAITING = "agent_waiting"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    RUN_PAUSED = "run_paused"
    RUN_CANCELLED = "run_cancelled"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    THINKING = "thinking"
