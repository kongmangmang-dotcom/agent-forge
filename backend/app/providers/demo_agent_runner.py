"""Demo coding agent — JSONL stdout for local testing without Codex/Cursor installed."""

from __future__ import annotations

import json
import sys
import time


def emit(event_type: str, content: str, **metadata: str) -> None:
    print(json.dumps({"type": event_type, "content": content, "metadata": metadata}), flush=True)


def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else "demo task"
    workspace = sys.argv[2] if len(sys.argv) > 2 else "."

    emit("session_created", f"Demo CLI 会话已创建（workspace={workspace}）")
    emit("task_started", f"开始执行: {prompt[:120]}")
    time.sleep(0.3)
    emit("thinking_update", "扫描工作区并分析任务…")
    time.sleep(0.4)
    # Keep assistant payload short — full prompts (with upstream summaries) can
    # exceed asyncio StreamReader line limits when echoed back as JSONL.
    preview = prompt if len(prompt) <= 240 else prompt[:240] + "…"
    emit(
        "assistant_message",
        f"Demo Agent 完成步骤。任务摘要：{preview}",
    )
    time.sleep(0.3)

    emit(
        "file_changed",
        "创建 demo_output.txt",
        path="demo_output.txt",
        action="created",
        lines_summary="+12",
        diff="+# Demo output\n+task completed",
    )
    time.sleep(0.2)
    emit("command_started", "运行 echo 验证", command="echo ok")
    time.sleep(0.2)
    emit("command_finished", "echo ok → 0", command="echo ok")
    emit("agent_completed", "Demo 任务完成")


if __name__ == "__main__":
    main()
