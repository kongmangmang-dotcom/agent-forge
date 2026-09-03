"""Generate daily work report from today's schedule tasks into 工作总结 KB."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.knowledge import KnowledgeDocumentCreate
from app.services.knowledge_chat import chat_backend_name, chat_complete
from app.services.knowledge_service import KnowledgeService
from app.services.schedule_service import ScheduleService

logger = logging.getLogger(__name__)

_NOTE_BODY_MAX = 2500
_TASK_DUMP_MAX = 14000


def app_zone() -> ZoneInfo:
    try:
        return ZoneInfo((settings.app_tz or "Asia/Shanghai").strip() or "Asia/Shanghai")
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def calendar_today() -> date:
    return datetime.now(app_zone()).date()


def report_doc_name(day: date) -> str:
    return f"工作日报 {day.isoformat()}"


def _truncate(text: str, limit: int) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def _build_source_markdown(day: date, tasks: list) -> str:
    lines = [
        f"# 今日任务素材 · {day.isoformat()}",
        "",
        f"共 {len(tasks)} 个任务。",
        "",
    ]
    for i, task in enumerate(tasks, 1):
        done = sum(1 for p in task.plan_items if p.status == "done")
        total = len(task.plan_items)
        lines.extend(
            [
                f"## {i}. {task.title}",
                f"- 状态：{task.status}",
                f"- 优先级：{task.priority}",
                f"- 步骤：{done}/{total}",
            ]
        )
        if task.workflow_title:
            lines.append(f"- 工作流：{task.workflow_title}")
        req = (task.requirement or "").strip()
        if req:
            lines.append("- 需求：")
            lines.append(_truncate(req, 1200))
        summary = (task.summary or "").strip()
        if summary:
            lines.append(f"- 摘要：{_truncate(summary, 600)}")
        if task.plan_items:
            lines.append("- 计划步骤：")
            for p in task.plan_items:
                lines.append(f"  - [{p.status}] {p.title}")
        if task.notes:
            lines.append("- 笔记：")
            for n in task.notes:
                title = n.title or ("文件" if n.kind == "file" else "笔记")
                body = _truncate(n.body or "", _NOTE_BODY_MAX)
                lines.append(f"  - {title}" + (f"：{body}" if body else ""))
        if task.memories:
            lines.append("- 记忆：")
            for m in task.memories:
                pin = "📌 " if m.pinned else ""
                lines.append(f"  - {pin}{_truncate(m.content, 400)}")
        lines.append("")
    raw = "\n".join(lines).strip()
    return _truncate(raw, _TASK_DUMP_MAX)


def _extractive_report(day: date, source: str, task_count: int) -> str:
    return "\n".join(
        [
            f"# 工作日报 · {day.isoformat()}",
            "",
            f"> 自动生成（未配置 Chat API，使用摘录整理）。任务数：{task_count}。",
            "",
            "## 原始素材",
            "",
            source,
            "",
        ]
    )


_SYSTEM = """你是一名严谨的工作助理。请根据用户提供的「今日任务素材」撰写一份中文《工作日报》。
要求：
1. 使用 Markdown，标题为「# 工作日报 · YYYY-MM-DD」（日期与素材一致）。
2. 包含：今日概览、已完成、进行中/待办、关键产出（笔记与文档）、风险与阻塞、明日建议。
3. 只基于素材事实，不要编造未出现的内容；素材不足处写「素材未提及」。
4. 语言简洁，条目化，适合归档到知识库。"""


async def generate_daily_report(
    db: AsyncSession,
    *,
    plan_date: date | None = None,
    force: bool = False,
) -> dict:
    """Summarize the day's tasks and upsert into the 工作总结 knowledge base."""
    day = plan_date or calendar_today()
    kb_name = (settings.daily_report_kb_name or "工作总结").strip() or "工作总结"
    ks = KnowledgeService(db)
    kb = await ks.get_or_create_base_by_name(
        kb_name,
        description="每日工作总结与工作日报归档（系统默认）",
    )

    doc_name = report_doc_name(day)
    existing = await ks.find_document_by_name(kb.id, doc_name)
    if existing and not force:
        return {
            "plan_date": day.isoformat(),
            "knowledge_id": kb.id,
            "knowledge_name": kb.name,
            "document_id": existing.id,
            "document_name": existing.name,
            "skipped": True,
            "reason": "already_exists",
            "task_count": 0,
            "chat_backend": chat_backend_name(),
        }

    schedule = ScheduleService(db)
    summaries = await schedule.list_tasks(day)
    tasks = []
    for s in summaries:
        tasks.append(await schedule.get_task(s.id))

    if not tasks:
        # Still write a short stub so the day is recorded
        content = (
            f"# 工作日报 · {day.isoformat()}\n\n"
            f"> 当日无计划任务，未生成详细总结。\n"
        )
        chat_backend = "empty_day"
    else:
        source = _build_source_markdown(day, tasks)
        if chat_backend_name() == "openai_compatible":
            try:
                content = await chat_complete(
                    _SYSTEM,
                    f"日期：{day.isoformat()}\n\n{source}",
                )
                chat_backend = "openai_compatible"
            except Exception as exc:
                logger.warning("daily report LLM failed, fallback extractive: %s", exc)
                content = _extractive_report(day, source, len(tasks))
                chat_backend = f"extractive_fallback:{exc}"
        else:
            content = _extractive_report(day, source, len(tasks))
            chat_backend = "extractive"

    if existing:
        await ks.delete_document(existing.id)

    doc = await ks.create_document(
        kb.id,
        KnowledgeDocumentCreate(
            name=doc_name,
            content=content,
            segment_max_chars=800,
        ),
    )

    # Best-effort workspace copy for agents
    try:
        out_dir = Path("workspace/demo/.agentforge/daily-reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{day.isoformat()}.md").write_text(content, encoding="utf-8")
    except Exception:
        logger.exception("failed to write daily report file for %s", day)

    return {
        "plan_date": day.isoformat(),
        "knowledge_id": kb.id,
        "knowledge_name": kb.name,
        "document_id": doc.id,
        "document_name": doc.name,
        "skipped": False,
        "reason": None,
        "task_count": len(tasks),
        "chat_backend": chat_backend,
    }
