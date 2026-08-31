import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.ids import new_id
from app.domain.enums import EventType, RunStatus
from app.domain.provider import AgentConfig, AgentPermissions, AgentLimits, TaskPayload
from app.models.agent import AgentModel
from app.models.provider import ProviderModel
from app.models.run import AgentEventModel, AgentMessageModel, AgentRunModel, FileChangeModel
from app.providers.registry import registry
from app.services.event_publisher import EventPublisher
from app.services.run_session_registry import mark_cancelled, queue_inject, remove_session

logger = logging.getLogger(__name__)

_running_tasks: dict[str, asyncio.Task] = {}


class RunService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.publisher = EventPublisher(db)

    async def _load_agent(self, agent_id: str) -> tuple[AgentModel, ProviderModel]:
        result = await self.db.execute(
            select(AgentModel)
            .options(joinedload(AgentModel.provider))
            .where(AgentModel.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise NotFoundError("Agent", agent_id)
        if not agent.provider:
            raise ValidationError(f"Agent {agent_id} has no provider")
        return agent, agent.provider

    def _to_agent_config(self, agent: AgentModel) -> AgentConfig:
        perms = agent.permissions or {}
        limits = agent.limits or {}
        return AgentConfig(
            id=agent.id,
            name=agent.name,
            provider_id=agent.provider_id,
            model=agent.model,
            role=agent.role,
            system_prompt=agent.system_prompt,
            workspace_path=agent.workspace_path,
            permissions=AgentPermissions.model_validate(perms),
            limits=AgentLimits.model_validate(limits),
            streaming=agent.streaming,
        )

    async def create_and_start(
        self,
        agent_id: str,
        task_prompt: str,
        *,
        step_run_id: str | None = None,
        workspace_path: str | None = None,
    ) -> AgentRunModel:
        agent, provider = await self._load_agent(agent_id)
        provider_impl = registry.get(provider.kind)
        if not provider_impl:
            raise ValidationError(f"No provider adapter for kind: {provider.kind}")

        run_id = new_id("run")
        workspace = (workspace_path or "").strip() or agent.workspace_path or "."
        row = AgentRunModel(
            id=run_id,
            step_run_id=step_run_id,
            agent_id=agent_id,
            status=RunStatus.PENDING,
            task_prompt=task_prompt,
            workspace_path=workspace,
        )
        self.db.add(row)
        await self.db.flush()

        # user message
        self.db.add(
            AgentMessageModel(
                id=new_id("msg"),
                run_id=run_id,
                role="user",
                content=task_prompt,
            )
        )
        await self.db.flush()
        await self.db.commit()

        task = asyncio.create_task(self._execute_run(run_id, agent, provider))
        _running_tasks[run_id] = task
        return row

    async def _execute_run(self, run_id: str, agent: AgentModel, provider: ProviderModel) -> None:
        from app.db.session import SessionLocal

        async with SessionLocal() as session:
            svc = RunService(session)
            row = await session.get(AgentRunModel, run_id)
            if not row:
                return
            row.status = RunStatus.RUNNING
            row.started_at = datetime.now(timezone.utc)
            await session.commit()

            agent_cfg = svc._to_agent_config(agent)
            provider_cfg = registry.provider_config_from_model(provider)
            impl = registry.get(provider.kind)
            if not impl:
                await svc._fail(run_id, agent.id, f"Unknown provider kind: {provider.kind}")
                await session.commit()
                return

            task = TaskPayload(prompt=row.task_prompt)
            try:
                if hasattr(impl, "stream_events"):
                    async for event in impl.stream_events(provider_cfg, agent_cfg, run_id, task):
                        await svc._handle_event(run_id, agent.id, event)
                        await session.commit()
                        if event.type in (EventType.AGENT_COMPLETED, EventType.AGENT_FAILED, EventType.RUN_CANCELLED):
                            break
                else:
                    await svc._fail(run_id, agent.id, "Provider does not support streaming")
                    await session.commit()
                    return

                final = await session.get(AgentRunModel, run_id)
                if final and final.status == RunStatus.RUNNING:
                    final.status = RunStatus.COMPLETED
                    final.finished_at = datetime.now(timezone.utc)
                    await session.commit()
            except Exception as e:
                logger.exception("Run %s failed", run_id)
                await svc._fail(run_id, agent.id, str(e))
                await session.commit()
            finally:
                remove_session(run_id)
                _running_tasks.pop(run_id, None)

    async def _handle_event(self, run_id: str, agent_id: str, event) -> None:
        file_change = None
        if event.type == EventType.FILE_CHANGED:
            meta = event.metadata or {}
            file_change = {
                "path": meta.get("path", "unknown"),
                "action": meta.get("action", "modified"),
                "lines_summary": meta.get("lines_summary", ""),
                "diff": meta.get("diff"),
            }

        persist_msg = None
        if event.type in (EventType.ASSISTANT_MESSAGE, EventType.THINKING_UPDATE):
            persist_msg = event.content
            role = "thinking" if event.type == EventType.THINKING_UPDATE else "assistant"
        else:
            role = "assistant"

        await self.publisher.publish(
            run_id=run_id,
            agent_id=agent_id,
            event_type=str(event.type),
            content=event.content,
            status=str(event.status),
            metadata=dict(event.metadata or {}),
            persist_message=persist_msg,
            message_role=role,
            file_change=file_change,
        )

        row = await self.db.get(AgentRunModel, run_id)
        if row and event.type in (EventType.AGENT_FAILED, EventType.RUN_CANCELLED):
            row.status = RunStatus.FAILED if event.type == EventType.AGENT_FAILED else RunStatus.CANCELLED
            row.finished_at = datetime.now(timezone.utc)
        elif row and event.type == EventType.AGENT_COMPLETED:
            row.status = RunStatus.COMPLETED
            row.finished_at = datetime.now(timezone.utc)
            try:
                from app.services.task_note_sync import sync_markdown_notes_from_agent_run

                await sync_markdown_notes_from_agent_run(self.db, run_id)
            except Exception:
                logger.exception("markdown note sync failed for run %s", run_id)

    async def _fail(self, run_id: str, agent_id: str, message: str) -> None:
        row = await self.db.get(AgentRunModel, run_id)
        if row:
            row.status = RunStatus.FAILED
            row.finished_at = datetime.now(timezone.utc)
        await self.publisher.publish(
            run_id=run_id,
            agent_id=agent_id,
            event_type=EventType.AGENT_FAILED,
            content=message,
            status=RunStatus.FAILED,
        )

    async def get_run(self, run_id: str) -> AgentRunModel:
        row = await self.db.get(AgentRunModel, run_id)
        if not row:
            raise NotFoundError("Run", run_id)
        return row

    async def list_runs(self, status: str | None = None) -> list[AgentRunModel]:
        q = select(AgentRunModel).order_by(AgentRunModel.created_at.desc())
        if status:
            q = q.where(AgentRunModel.status == status)
        result = await self.db.execute(q.limit(50))
        return list(result.scalars().all())

    async def inject_message(self, run_id: str, content: str) -> None:
        row = await self.get_run(run_id)
        if row.status != RunStatus.RUNNING:
            raise ConflictError("RUN_NOT_RUNNING", "无法注入消息：Run 未处于 running 状态")

        agent = await self.db.get(AgentModel, row.agent_id)
        provider = await self.db.get(ProviderModel, agent.provider_id) if agent else None
        impl = registry.get(provider.kind) if provider else None

        await self.publisher.publish(
            run_id=run_id,
            agent_id=row.agent_id,
            event_type="user_message",
            content=content,
            persist_message=content,
            message_role="user",
        )

        if impl:
            from app.domain.provider import SessionHandle

            handle = SessionHandle(run_id=run_id, provider_kind=provider.kind)
            await impl.inject_message(handle, content)

    async def cancel_run(self, run_id: str) -> AgentRunModel:
        row = await self.get_run(run_id)
        if row.status in (
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        ):
            return row
        if row.status not in (RunStatus.RUNNING, RunStatus.PENDING):
            raise ConflictError("RUN_NOT_RUNNING", "Run 已结束，无法取消")
        mark_cancelled(run_id)
        agent = await self.db.get(AgentModel, row.agent_id)
        provider = await self.db.get(ProviderModel, agent.provider_id) if agent else None
        impl = registry.get(provider.kind) if provider else None
        if impl:
            from app.domain.provider import SessionHandle

            await impl.cancel(SessionHandle(run_id=run_id, provider_kind=provider.kind))
        row.status = RunStatus.CANCELLED
        row.finished_at = datetime.now(timezone.utc)
        return row
