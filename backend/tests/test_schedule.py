"""Schedule / daily task API — requires PostgreSQL."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _require_db(client: AsyncClient) -> None:
    resp = await client.get("/health")
    if resp.json().get("database") != "ok":
        pytest.skip("PostgreSQL not available")


async def test_schedule_crud_and_plan(client: AsyncClient):
    await _require_db(client)

    created = await client.post(
        "/api/v1/schedule/tasks",
        json={"title": "pytest-schedule-task", "with_plan": False},
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert created.json()["plan_items"]

    listed = await client.get("/api/v1/schedule/tasks")
    assert listed.status_code == 200
    assert any(t["id"] == task_id for t in listed.json()["items"])

    planned = await client.post(
        "/api/v1/schedule/tasks/plan-today",
        json={"goal": "pytest 实现登录功能"},
    )
    assert planned.status_code == 200, planned.text
    task = planned.json()["task"]
    assert task["type"] == "dev"
    assert len(task["plan_items"]) >= 3

    regen = await client.post(f"/api/v1/schedule/tasks/{task_id}/regenerate-plan")
    assert regen.status_code == 200, regen.text
    assert len(regen.json()["plan_items"]) >= 1

    deleted = await client.delete(f"/api/v1/schedule/tasks/{task_id}")
    assert deleted.status_code == 204
    await client.delete(f"/api/v1/schedule/tasks/{task['id']}")

