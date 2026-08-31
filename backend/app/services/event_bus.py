import asyncio
from collections import defaultdict
from typing import Any


class EventBus:
    """In-memory pub/sub for SSE (single API instance)."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, run_id: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._queues[run_id].append(q)
        return q

    async def unsubscribe(self, run_id: str, q: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            if run_id in self._queues:
                self._queues[run_id] = [x for x in self._queues[run_id] if x is not q]
                if not self._queues[run_id]:
                    del self._queues[run_id]

    async def publish(self, run_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._queues.get(run_id, []))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


event_bus = EventBus()
