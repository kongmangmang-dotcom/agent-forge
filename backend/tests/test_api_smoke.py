import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "agent-forge-api"
    assert body["status"] in ("ok", "degraded")


@pytest.mark.asyncio
async def test_role_templates(client: AsyncClient):
    resp = await client.get("/api/v1/agents/roles/templates")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 6
    assert items[0]["role"] == "planner"
