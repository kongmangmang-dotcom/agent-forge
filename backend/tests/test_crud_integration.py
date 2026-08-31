"""Integration tests — require PostgreSQL on localhost:5434 (docker compose up postgres)."""

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


async def _require_db(client: AsyncClient) -> None:
    resp = await client.get("/health")
    if resp.json().get("database") != "ok":
        pytest.skip("PostgreSQL not available")


async def test_provider_crud(client: AsyncClient):
    await _require_db(client)
    create = await client.post(
        "/api/v1/providers",
        json={
            "kind": "openai",
            "type": "model_api",
            "name": "Test OpenAI",
            "endpoint": "https://api.openai.com/v1",
            "default_model": "gpt-4o",
            "config": {"api_key_ref": "env:OPENAI_API_KEY"},
            "capabilities": ["test"],
        },
    )
    assert create.status_code == 201
    provider = create.json()
    provider_id = provider["id"]
    assert provider_id.startswith("prv_")

    listed = await client.get("/api/v1/providers")
    assert any(p["id"] == provider_id for p in listed.json()["items"])

    got = await client.get(f"/api/v1/providers/{provider_id}")
    assert got.status_code == 200

    deleted = await client.delete(f"/api/v1/providers/{provider_id}")
    assert deleted.status_code == 204


async def test_agent_crud(client: AsyncClient):
    await _require_db(client)
    prv = await client.post(
        "/api/v1/providers",
        json={
            "kind": "openai",
            "type": "model_api",
            "name": "Agent Test Provider",
            "config": {},
        },
    )
    provider_id = prv.json()["id"]

    create = await client.post(
        "/api/v1/agents",
        json={
            "name": "test-agent-week1",
            "provider_id": provider_id,
            "model": "gpt-4o",
            "role": "planner",
        },
    )
    assert create.status_code == 201
    agent_id = create.json()["id"]
    assert agent_id.startswith("agt_")

    listed = await client.get("/api/v1/agents")
    assert any(a["id"] == agent_id for a in listed.json()["items"])

    await client.delete(f"/api/v1/agents/{agent_id}")
    await client.delete(f"/api/v1/providers/{provider_id}")
