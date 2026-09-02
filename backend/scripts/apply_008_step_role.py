import asyncio

import asyncpg

DSN = "postgresql://agentforge:agentforge@localhost:5434/agentforge"
SQL = "ALTER TABLE workflow_step_def ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT ''"


async def main() -> None:
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute(SQL)
        print("migration 008 applied")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
