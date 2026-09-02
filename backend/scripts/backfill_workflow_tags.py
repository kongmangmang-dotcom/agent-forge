"""Backfill options.tags on existing workflow definitions (计划 / 开发)."""
from __future__ import annotations

import asyncio
import json

import asyncpg

DSN = "postgresql://agentforge:agentforge@localhost:5434/agentforge"


async def main() -> None:
    conn = await asyncpg.connect(DSN)
    try:
        rows = await conn.fetch("SELECT id, name, options FROM workflow_definition")
        for row in rows:
            options = row["options"]
            if isinstance(options, str):
                options = json.loads(options)
            options = dict(options or {})
            tags = options.get("tags")
            if isinstance(tags, list) and tags:
                print("skip", row["name"], tags)
                continue
            name = (row["name"] or "").lower()
            if "plan" in name or options.get("plan_only") or options.get("is_default_dev_plan"):
                new_tags = ["计划"]
            else:
                new_tags = ["开发"]
            options["tags"] = new_tags
            await conn.execute(
                "UPDATE workflow_definition SET options = $1::jsonb WHERE id = $2",
                json.dumps(options, ensure_ascii=False),
                row["id"],
            )
            print("updated", row["name"], "->", new_tags)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
