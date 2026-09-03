"""Background loop: generate daily work report at configured local time."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.daily_report_service import app_zone, generate_daily_report
from app.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


def seconds_until_next_report() -> float:
    tz = app_zone()
    now = datetime.now(tz)
    hour = int(settings.daily_report_hour)
    minute = int(settings.daily_report_minute)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


async def ensure_default_work_summary_kb() -> None:
    name = (settings.daily_report_kb_name or "工作总结").strip() or "工作总结"
    async with SessionLocal() as db:
        ks = KnowledgeService(db)
        await ks.get_or_create_base_by_name(
            name,
            description="每日工作总结与工作日报归档（系统默认）",
        )


async def run_daily_report_once(*, force: bool = False) -> dict:
    async with SessionLocal() as db:
        result = await generate_daily_report(db, force=force)
        return result


async def run_daily_report_loop() -> None:
    if not settings.daily_report_enabled:
        logger.info("daily report scheduler disabled")
        return

    logger.info(
        "daily report scheduler started (tz=%s hour=%s:%02d kb=%s)",
        settings.app_tz,
        settings.daily_report_hour,
        settings.daily_report_minute,
        settings.daily_report_kb_name,
    )
    while True:
        delay = seconds_until_next_report()
        logger.info("daily report next run in %.0f seconds", delay)
        try:
            await asyncio.sleep(delay)
            result = await run_daily_report_once(force=True)
            logger.info("daily report finished: %s", result)
        except asyncio.CancelledError:
            logger.info("daily report scheduler cancelled")
            raise
        except Exception:
            logger.exception("daily report job failed")
            await asyncio.sleep(60)
