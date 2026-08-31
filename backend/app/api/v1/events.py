import asyncio
import json

from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

from app.services.event_bus import event_bus

router = APIRouter(prefix="/events", tags=["events"])


async def event_generator(run_id: str):
    yield {
        "event": "connected",
        "data": json.dumps({"run_id": run_id}),
    }

    queue = await event_bus.subscribe(run_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield {
                    "event": event.get("type", "message"),
                    "id": str(event.get("id", "")),
                    "data": json.dumps(event, default=str),
                }
                if event.get("type") in ("agent_completed", "agent_failed", "run_cancelled"):
                    await asyncio.sleep(0.5)
                    break
            except TimeoutError:
                yield {"event": "heartbeat", "data": json.dumps({"run_id": run_id})}
    finally:
        await event_bus.unsubscribe(run_id, queue)


@router.get("/stream")
async def stream_events(
    run_id: str | None = Query(None),
    workflow_run_id: str | None = Query(None),
):
    if workflow_run_id and not run_id:
        return {"error": "workflow_run_id SSE not implemented yet; use run_id"}
    if not run_id:
        return {"error": "run_id required"}
    return EventSourceResponse(event_generator(run_id))
