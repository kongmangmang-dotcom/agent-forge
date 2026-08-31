"""Codex CLI `--json` 事件 → 平台 AgentEvent 映射。

Codex 0.150.x `codex exec --json` 输出 JSONL，事件形态（实测）：

  {"type":"thread.started","thread_id":"..."}
  {"type":"turn.started"}
  {"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"..."}}
  {"type":"item.started","item":{"id":"item_1","type":"file_change","changes":[{"path":"...","kind":"add"}],"status":"in_progress"}}
  {"type":"item.completed","item":{"id":"item_1","type":"file_change","changes":[{"path":"...","kind":"add"}],"status":"completed"}}
  {"type":"item.started","item":{"id":"item_2","type":"command_execution","command":"...","exit_code":null,"status":"in_progress"}}
  {"type":"item.completed","item":{"id":"item_2","type":"command_execution","command":"...","aggregated_output":"...","exit_code":0,"status":"completed"}}
  {"type":"turn.completed","usage":{"input_tokens":...,"output_tokens":...}}
      → 映射为 agent_completed；CliCodingProvider 随即结束 CLI 进程（避免收尾卡死）。

其中 item.type 还可能为 reasoning / tool_call / custom_tool_call / web_search 等。
"""

from datetime import datetime, timezone
from typing import Any

from app.domain.enums import EventType, RunStatus
from app.domain.provider import AgentEvent

_KIND_TO_ACTION = {
    "add": "created",
    "edit": "modified",
    "remove": "deleted",
}


def map_codex_event(parsed: dict[str, Any], run_id: str, agent_id: str) -> list[AgentEvent]:
    """把一个 codex JSON 事件翻译为 0..n 个平台事件。"""
    etype = parsed.get("type")
    now = datetime.now(timezone.utc)

    if etype == "thread.started":
        # thread_id 可用于后续 `codex exec resume`（Week 4 纠正指令）。
        # 不重复发 session_created（框架已在进程启动时发过）。
        return []

    if etype == "turn.started":
        return []

    if etype == "turn.completed":
        # 一轮 exec 任务已完成。由 CliCodingProvider 据此结束进程并发 agent_completed；
        # 这里带上 usage，避免只靠进程退出（Codex 收尾拉插件时可能卡住）。
        usage = parsed.get("usage") or {}
        meta = {k: str(v) for k, v in usage.items() if v is not None}
        return [
            _event(
                run_id,
                agent_id,
                EventType.AGENT_COMPLETED,
                RunStatus.COMPLETED,
                "Codex turn completed",
                meta,
                now,
            )
        ]

    if etype not in ("item.started", "item.completed"):
        return []

    item = parsed.get("item") or {}
    itype = item.get("type")

    if itype == "agent_message":
        if etype != "item.completed":
            return []
        text = (item.get("text") or "").strip()
        if not text:
            return []
        return [_event(run_id, agent_id, EventType.ASSISTANT_MESSAGE, RunStatus.RUNNING, text, {}, now)]

    if itype == "reasoning":
        if etype != "item.completed":
            return []
        text = (item.get("text") or item.get("summary") or "").strip()
        if not text:
            return []
        return [_event(run_id, agent_id, EventType.THINKING_UPDATE, RunStatus.RUNNING, text, {}, now)]

    if itype == "file_change":
        if etype != "item.completed":
            return []
        events: list[AgentEvent] = []
        for change in item.get("changes") or []:
            path = change.get("path") or ""
            kind = change.get("kind") or "edit"
            action = _KIND_TO_ACTION.get(kind, "modified")
            events.append(
                _event(
                    run_id,
                    agent_id,
                    EventType.FILE_CHANGED,
                    RunStatus.COMPLETED,
                    f"{action} {path}",
                    {"path": path, "action": action, "kind": kind},
                    now,
                )
            )
        return events

    if itype == "command_execution":
        command = item.get("command") or ""
        if etype == "item.started":
            return [
                _event(
                    run_id,
                    agent_id,
                    EventType.COMMAND_STARTED,
                    RunStatus.RUNNING,
                    command,
                    {"command": command},
                    now,
                )
            ]
        output = item.get("aggregated_output") or ""
        exit_code = item.get("exit_code")
        meta = {"command": command}
        if exit_code is not None:
            meta["exit_code"] = str(exit_code)
        return [
            _event(
                run_id,
                agent_id,
                EventType.COMMAND_FINISHED,
                RunStatus.COMPLETED,
                output,
                meta,
                now,
            )
        ]

    if itype in ("tool_call", "custom_tool_call"):
        if etype != "item.completed":
            return []
        name = item.get("name") or item.get("tool_name") or itype
        return [_event(run_id, agent_id, EventType.TOOL_CALL, RunStatus.COMPLETED, str(name), {}, now)]

    return []


def _event(
    run_id: str,
    agent_id: str,
    etype: EventType,
    status: RunStatus,
    content: str,
    metadata: dict[str, str],
    now: datetime,
) -> AgentEvent:
    return AgentEvent(
        run_id=run_id,
        agent_id=agent_id,
        type=etype,
        status=status,
        content=content,
        metadata=metadata,
        timestamp=now,
    )
