"""Workflow definition CRUD and DAG validation tests."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _require_db(client: AsyncClient) -> None:
    resp = await client.get("/health")
    if resp.json().get("database") != "ok":
        pytest.skip("PostgreSQL not available")


async def _create_demo_agent(client: AsyncClient) -> str:
    listed = await client.get("/api/v1/agents")
    items = listed.json()["items"]
    if items:
        return items[0]["id"]
    prv = await client.post(
        "/api/v1/providers",
        json={"kind": "demo_cli", "type": "coding_agent", "name": "WF Test Provider"},
    )
    assert prv.status_code == 201
    agent = await client.post(
        "/api/v1/agents",
        json={
            "name": "wf-test-agent",
            "provider_id": prv.json()["id"],
            "role": "developer",
        },
    )
    assert agent.status_code == 201
    return agent.json()["id"]


async def test_workflow_definition_crud(client: AsyncClient):
    await _require_db(client)
    agent_id = await _create_demo_agent(client)

    create = await client.post(
        "/api/v1/workflows/definitions",
        json={
            "name": "wf-linear-test",
            "title": "Linear Workflow",
            "description": "plan -> dev -> test",
            "steps": [
                {
                    "step_key": "plan",
                    "label": "Plan",
                    "agent_id": agent_id,
                    "depends_on": [],
                    "sort_order": 0,
                },
                {
                    "step_key": "dev",
                    "label": "Dev",
                    "agent_id": agent_id,
                    "depends_on": ["plan"],
                    "sort_order": 1,
                },
            ],
        },
    )
    assert create.status_code == 201, create.text
    wf_id = create.json()["id"]
    assert wf_id.startswith("wfd_")
    assert len(create.json()["steps"]) == 2

    listed = await client.get("/api/v1/workflows/definitions")
    assert any(w["id"] == wf_id for w in listed.json()["items"])

    got = await client.get(f"/api/v1/workflows/definitions/{wf_id}")
    assert got.status_code == 200
    assert got.json()["steps"][1]["depends_on"] == ["plan"]

    deleted = await client.delete(f"/api/v1/workflows/definitions/{wf_id}")
    assert deleted.status_code == 204


async def test_workflow_definition_update(client: AsyncClient):
    await _require_db(client)
    agent_id = await _create_demo_agent(client)

    create = await client.post(
        "/api/v1/workflows/definitions",
        json={
            "name": "wf-update-test",
            "title": "Before",
            "description": "old",
            "steps": [
                {
                    "step_key": "only",
                    "label": "Only",
                    "agent_id": agent_id,
                    "depends_on": [],
                    "sort_order": 0,
                },
            ],
        },
    )
    if create.status_code == 409:
        listed = await client.get("/api/v1/workflows/definitions")
        wf_id = next(w["id"] for w in listed.json()["items"] if w["name"] == "wf-update-test")
    else:
        assert create.status_code == 201, create.text
        wf_id = create.json()["id"]

    updated = await client.patch(
        f"/api/v1/workflows/definitions/{wf_id}",
        json={
            "title": "After",
            "description": "new desc",
            "steps": [
                {
                    "step_key": "a",
                    "label": "A",
                    "agent_id": agent_id,
                    "depends_on": [],
                    "sort_order": 0,
                },
                {
                    "step_key": "b",
                    "label": "B",
                    "agent_id": agent_id,
                    "depends_on": ["a"],
                    "sort_order": 1,
                },
            ],
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["title"] == "After"
    assert body["description"] == "new desc"
    assert len(body["steps"]) == 2
    assert body["steps"][1]["depends_on"] == ["a"]

    got = await client.get(f"/api/v1/workflows/definitions/{wf_id}")
    assert got.json()["title"] == "After"

    await client.delete(f"/api/v1/workflows/definitions/{wf_id}")


async def test_workflow_rejects_cycle(client: AsyncClient):
    await _require_db(client)
    agent_id = await _create_demo_agent(client)

    resp = await client.post(
        "/api/v1/workflows/definitions",
        json={
            "name": "wf-cycle-test",
            "title": "Cycle",
            "steps": [
                {
                    "step_key": "a",
                    "label": "A",
                    "agent_id": agent_id,
                    "depends_on": ["b"],
                },
                {
                    "step_key": "b",
                    "label": "B",
                    "agent_id": agent_id,
                    "depends_on": ["a"],
                },
            ],
        },
    )
    assert resp.status_code == 400
    assert "cycle" in resp.json()["error"]["message"].lower()
