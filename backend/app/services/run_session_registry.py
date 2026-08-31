import asyncio
from dataclasses import dataclass, field

from app.domain.provider import SessionHandle


@dataclass
class ActiveRunSession:
    handle: SessionHandle
    agent_id: str
    provider_kind: str
    inject_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    cancelled: bool = False
    process: asyncio.subprocess.Process | None = None


_sessions: dict[str, ActiveRunSession] = {}


def register_session(run_id: str, session: ActiveRunSession) -> None:
    _sessions[run_id] = session


def get_session(run_id: str) -> ActiveRunSession | None:
    return _sessions.get(run_id)


def remove_session(run_id: str) -> None:
    _sessions.pop(run_id, None)


async def queue_inject(run_id: str, content: str) -> bool:
    s = _sessions.get(run_id)
    if not s:
        return False
    await s.inject_queue.put(content)
    return True


def mark_cancelled(run_id: str) -> None:
    s = _sessions.get(run_id)
    if s:
        s.cancelled = True
