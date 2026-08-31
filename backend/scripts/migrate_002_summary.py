"""Apply 002_step_run_summary migration."""
import asyncio

from sqlalchemy import text

from app.db.session import engine


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE step_run "
                "ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT ''"
            )
        )
    print("ok")


if __name__ == "__main__":
    asyncio.run(main())
