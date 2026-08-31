import asyncio
import json
import logging
import shutil
import sys
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.enums import EventType, RunStatus
from app.domain.provider import (
    AgentConfig,
    AgentEvent,
    AgentProvider,
    ConnectionResult,
    FileChange,
    ProviderConfig,
    SessionHandle,
    TaskPayload,
)
from app.providers.codex_event_mapper import map_codex_event
from app.services.run_session_registry import (
    ActiveRunSession,
    get_session,
    register_session,
    remove_session,
)

logger = logging.getLogger(__name__)


async def _stop_process(proc: asyncio.subprocess.Process, *, grace_seconds: float = 5.0) -> None:
    """Terminate CLI process (and Windows child tree) so turn completion cannot hang forever."""
    if proc.returncode is not None:
        return
    try:
        if sys.platform == "win32" and proc.pid:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/T",
                "/F",
                "/PID",
                str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
        else:
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
        except TimeoutError:
            proc.kill()
            await proc.wait()
    except ProcessLookupError:
        pass
    except Exception:
        logger.info("stop_process failed for pid=%s", getattr(proc, "pid", None), exc_info=True)
        try:
            proc.kill()
        except Exception:
            pass


def _parse_jsonl_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"type": EventType.ASSISTANT_MESSAGE, "content": line, "metadata": {}}


class CliCodingProvider:
    """Base adapter for subprocess-based coding agents (Codex, Cursor, OpenCode, Demo)."""

    provider_kind: str = "cli_base"
    default_command: str = ""
    default_args: list[str] = []
    # 是否通过 stdin 与子进程交互（用于 inject_message）。Codex 非交互 exec 会把
    # stdin 当 prompt 追加而非运行中对话，因此关闭 stdin，避免子进程阻塞等待输入。
    uses_stdin: bool = True

    def _command(self, config: ProviderConfig) -> str:
        return str(config.config.get("cli_command") or self.default_command)

    def _extra_args(self, config: ProviderConfig) -> list[str]:
        raw = config.config.get("cli_args")
        if isinstance(raw, list):
            return [str(x) for x in raw]
        return list(self.default_args)

    def _resolve_exec(self, cmd: str) -> list[str]:
        """把 CLI 命令解析为可直接交给 create_subprocess_exec 的执行前缀。

        Windows 上 npm 全局命令是 .cmd/.bat shim，CreateProcess 无法直接执行，
        需经 cmd.exe 转发；其余情况直接执行解析到的路径。
        """
        resolved = shutil.which(cmd)
        if not resolved:
            return [cmd]
        if sys.platform == "win32" and resolved.lower().endswith((".cmd", ".bat")):
            return ["cmd.exe", "/c", resolved]
        return [resolved]

    async def test_connection(self, config: ProviderConfig) -> ConnectionResult:
        cmd = self._command(config)
        if not cmd:
            return ConnectionResult(ok=False, message="cli_command not configured")
        if config.kind == "demo_cli":
            return ConnectionResult(ok=True, message="Demo CLI (Python runner, no external binary)")
        path = shutil.which(cmd)
        if not path:
            return ConnectionResult(
                ok=False,
                message=f"Command not found: {cmd}. Install the CLI or use kind=demo_cli for testing.",
            )
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._resolve_exec(cmd),
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            lines = stdout.decode(errors="replace").strip().splitlines()
            ver = lines[0] if lines else "ok"
            if proc.returncode == 0:
                return ConnectionResult(ok=True, message=f"CLI ok: {ver}")
            return ConnectionResult(ok=False, message=f"CLI exited with code {proc.returncode}")
        except TimeoutError:
            return ConnectionResult(ok=False, message=f"CLI timed out: {cmd}")
        except Exception as e:
            return ConnectionResult(ok=False, message=f"CLI check failed: {e}")

    async def create_session(self, agent: AgentConfig, run_id: str) -> SessionHandle:
        return SessionHandle(run_id=run_id, provider_kind=self.provider_kind)

    async def send_task(self, session: SessionHandle, task: TaskPayload) -> None:
        pass  # started in stream_events

    async def inject_message(self, session: SessionHandle, content: str) -> None:
        active = get_session(session.run_id)
        if not active:
            return
        await active.inject_queue.put(content)
        if active.process and active.process.stdin:
            try:
                active.process.stdin.write(content.encode() + b"\n")
                await active.process.stdin.drain()
            except Exception as e:
                logger.warning("inject stdin failed: %s", e)

    async def pause(self, session: SessionHandle) -> None:
        pass

    async def resume(self, session: SessionHandle) -> None:
        pass

    async def cancel(self, session: SessionHandle) -> None:
        active = get_session(session.run_id)
        if active and active.process and active.process.returncode is None:
            active.process.terminate()

    async def collect_file_changes(self, session: SessionHandle) -> list[FileChange]:
        return []

    def _build_argv(self, config: ProviderConfig, agent: AgentConfig, prompt: str) -> list[str]:
        raise NotImplementedError

    def _map_event(self, parsed: dict[str, Any], run_id: str, agent_id: str) -> list[AgentEvent]:
        """把一行解析后的 JSONL 映射为 0..n 个平台事件（默认按平台自定义 JSONL 格式）。"""
        etype = str(parsed.get("type", EventType.ASSISTANT_MESSAGE))
        meta = parsed.get("metadata") or {}
        if isinstance(meta, dict):
            meta = {str(k): str(v) for k, v in meta.items()}
        if etype == EventType.AGENT_COMPLETED:
            status = RunStatus.COMPLETED
        elif etype == EventType.AGENT_FAILED:
            status = RunStatus.FAILED
        else:
            status = RunStatus.RUNNING
        return [
            AgentEvent(
                run_id=run_id,
                agent_id=agent_id,
                type=etype,
                status=status,
                content=str(parsed.get("content", "")),
                metadata=meta,
                timestamp=datetime.now(timezone.utc),
            )
        ]

    async def stream_events(
        self,
        config: ProviderConfig,
        agent: AgentConfig,
        run_id: str,
        task: TaskPayload,
    ) -> AsyncIterator[AgentEvent]:
        handle = SessionHandle(run_id=run_id, provider_kind=self.provider_kind)
        workspace = agent.workspace_path or "."
        Path(workspace).mkdir(parents=True, exist_ok=True)

        argv = self._build_argv(config, agent, task.prompt)
        logger.info("Starting CLI: %s (cwd=%s)", argv, workspace)

        stdin = asyncio.subprocess.PIPE if self.uses_stdin else asyncio.subprocess.DEVNULL
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=stdin,
            limit=1024 * 1024,
        )

        active = ActiveRunSession(
            handle=handle,
            agent_id=agent.id,
            provider_kind=self.provider_kind,
            process=proc,
        )
        register_session(run_id, active)

        yield AgentEvent(
            run_id=run_id,
            agent_id=agent.id,
            type=EventType.SESSION_CREATED,
            status=RunStatus.RUNNING,
            content=f"CLI 进程已启动: {' '.join(argv)}",
        )
        yield AgentEvent(
            run_id=run_id,
            agent_id=agent.id,
            type=EventType.TASK_STARTED,
            status=RunStatus.RUNNING,
            content=task.prompt[:500],
        )

        stderr_chunks: list[str] = []

        async def read_stderr() -> None:
            assert proc.stderr
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                stderr_chunks.append(line.decode(errors="replace"))

        stderr_task = asyncio.create_task(read_stderr())

        # Provider 在 JSONL 里已声明回合结束（如 Codex turn.completed）时置位，
        # 随后强停进程，避免收尾阶段（插件同步等）把 Run 挂死。
        provider_completed = False
        completed_event: AgentEvent | None = None
        early_terminal: AgentEvent | None = None

        assert proc.stdout
        while True:
            if active.cancelled:
                await _stop_process(proc)
                break
            # 处理排队中的纠正指令（仅限使用 stdin 交互的 Provider）
            if self.uses_stdin:
                try:
                    inject = active.inject_queue.get_nowait()
                    yield AgentEvent(
                        run_id=run_id,
                        agent_id=agent.id,
                        type=EventType.ASSISTANT_MESSAGE,
                        status=RunStatus.RUNNING,
                        content=f"已收到纠正指令：{inject}",
                    )
                    if active.process and active.process.stdin:
                        try:
                            active.process.stdin.write(inject.encode() + b"\n")
                            await active.process.stdin.drain()
                        except Exception:
                            pass
                except asyncio.QueueEmpty:
                    pass

            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=0.5)
            except TimeoutError:
                continue
            if not line:
                break
            parsed = _parse_jsonl_line(line.decode(errors="replace"))
            if not parsed:
                continue

            stop_after_batch = False
            for event in self._map_event(parsed, run_id, agent.id):
                if event.type == EventType.AGENT_COMPLETED:
                    provider_completed = True
                    completed_event = event
                    stop_after_batch = True
                    continue
                if event.type in (EventType.AGENT_FAILED, EventType.RUN_CANCELLED):
                    early_terminal = event
                    yield event
                    stop_after_batch = True
                    break
                yield event

            if stop_after_batch:
                await _stop_process(proc)
                break

        if not stderr_task.done():
            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass
        else:
            await stderr_task

        if proc.returncode is None:
            await _stop_process(proc)
        code = proc.returncode if proc.returncode is not None else await proc.wait()
        remove_session(run_id)

        if early_terminal is not None:
            return
        if active.cancelled:
            yield AgentEvent(
                run_id=run_id,
                agent_id=agent.id,
                type=EventType.RUN_CANCELLED,
                status=RunStatus.CANCELLED,
                content="Run 已取消",
            )
        elif provider_completed or code == 0:
            yield completed_event or AgentEvent(
                run_id=run_id,
                agent_id=agent.id,
                type=EventType.AGENT_COMPLETED,
                status=RunStatus.COMPLETED,
                content="Agent 执行完成",
            )
        else:
            err = "".join(stderr_chunks)[-2000:]
            yield AgentEvent(
                run_id=run_id,
                agent_id=agent.id,
                type=EventType.AGENT_FAILED,
                status=RunStatus.FAILED,
                content=err or f"CLI exited with code {code}",
            )


class DemoCliProvider(CliCodingProvider):
    provider_kind = "demo_cli"
    default_command = "python"

    def _build_argv(self, config: ProviderConfig, agent: AgentConfig, prompt: str) -> list[str]:
        import sys

        runner = Path(__file__).with_name("demo_agent_runner.py")
        return [sys.executable, str(runner), prompt, agent.workspace_path or "."]


class CodexCliProvider(CliCodingProvider):
    provider_kind = "codex_cli"
    default_command = "codex"
    # codex 0.150+ 已移除 --full-auto；--json 输出 JSONL 事件流（见 codex_event_mapper）。
    default_args = ["exec", "--json"]

    uses_stdin = False

    def _build_argv(self, config: ProviderConfig, agent: AgentConfig, prompt: str) -> list[str]:
        cmd = self._command(config)
        args = self._extra_args(config)
        sandbox = str(config.config.get("sandbox") or "workspace-write")
        return [*self._resolve_exec(cmd), *args, "--sandbox", sandbox, "--skip-git-repo-check", prompt]

    def _map_event(self, parsed: dict[str, Any], run_id: str, agent_id: str) -> list[AgentEvent]:
        return map_codex_event(parsed, run_id, agent_id)


class OpencodeCliProvider(CliCodingProvider):
    provider_kind = "opencode_cli"
    default_command = "opencode"
    default_args = ["run"]

    def _build_argv(self, config: ProviderConfig, agent: AgentConfig, prompt: str) -> list[str]:
        cmd = self._command(config)
        args = self._extra_args(config)
        return [*self._resolve_exec(cmd), *args, prompt]


class CursorCliProvider(CliCodingProvider):
    provider_kind = "cursor_cli"
    default_command = "cursor"
    default_args = ["agent"]

    def _build_argv(self, config: ProviderConfig, agent: AgentConfig, prompt: str) -> list[str]:
        cmd = self._command(config)
        args = self._extra_args(config)
        return [*self._resolve_exec(cmd), *args, prompt]
