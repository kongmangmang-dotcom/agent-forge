"""Apply 013_daily_task_tags migration."""
import asyncio
from pathlib import Path

from sqlalchemy import text

from app.db.session import SessionLocal


async def main() -> None:
    raw = Path("migrations/013_daily_task_tags.sql").read_text(encoding="utf-8")
    lines = []
    for line in raw.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    body = "\n".join(lines)
    stmts = [s.strip() for s in body.split(";") if s.strip()]
    async with SessionLocal() as s:
        for stmt in stmts:
            await s.execute(text(stmt))
        await s.commit()
        rows = (
            await s.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name='daily_task' AND column_name='tags'"
                )
            )
        ).fetchall()
        print("tags", rows)


if __name__ == "__main__":
    asyncio.run(main())
