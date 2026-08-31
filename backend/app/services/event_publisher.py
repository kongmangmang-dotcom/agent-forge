from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.domain.enums import EventType, MessageRole
from app.models.run import AgentEventModel, AgentMessageModel, FileChangeModel
from app.services.event_bus import event_bus


class EventPublisher:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def publish(
        self,
        *,
        run_id: str,
        agent_id: str,
        event_type: str,
        content: str,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
        persist_message: str | None = None,
        message_role: str = MessageRole.ASSISTANT,
        file_change: dict[str, str] | None = None,
    ) -> None:
        meta = metadata or {}
        row = AgentEventModel(
            run_id=run_id,
            type=event_type,
            status=status,
            content=content,
            metadata_=meta,
        )
        self.db.add(row)
        await self.db.flush()

        if persist_message:
            self.db.add(
                AgentMessageModel(
                    id=new_id("msg"),
                    run_id=run_id,
                    role=message_role,
                    content=persist_message,
                )
            )

        if file_change:
            self.db.add(
                FileChangeModel(
                    run_id=run_id,
                    path=file_change.get("path", ""),
                    action=file_change.get("action", "modified"),
                    lines_summary=file_change.get("lines_summary", ""),
                    diff=file_change.get("diff"),
                )
            )

        await self.db.flush()

        payload = {
            "id": row.id,
            "run_id": run_id,
            "agent_id": agent_id,
            "type": event_type,
            "status": status,
            "content": content,
            "metadata": meta,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await event_bus.publish(run_id, payload)
