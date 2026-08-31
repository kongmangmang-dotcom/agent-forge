"""Workflow run orchestration — requires PostgreSQL + demo_cli agent."""

import asyncio

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _require_db(client: AsyncClient) -> None:
    resp = await client.get("/health")
    if resp.json().get("database") != "ok":
        pytest.skip("PostgreSQL not available")


async def _demo_agent_id(client: AsyncClient) -> str:
    agents = await client.get("/api/v1/agents")
    for item in agents.json()["items"]:
        if item["name"] == "demo-developer":
            return item["id"]
    pytest.skip("demo-developer agent not seeded")


async def test_workflow_run_linear_demo(client: AsyncClient):
    await _require_db(client)
    agent_id = await _demo_agent_id(client)

    wf_name = "wf-summary-inject-demo"
    listed = await client.get("/api/v1/workflows/definitions")
    existing = next((w for w in listed.json()["items"] if w["name"] == wf_name), None)
    steps_payload = [
        {
            "step_key": "step_a",
            "label": "Step A",
            "agent_id": agent_id,
            "depends_on": [],
            "sort_order": 0,
        },
        {
            "step_key": "step_b",
            "label": "Step B",
            "agent_id": agent_id,
            "depends_on": ["step_a"],
            "sort_order": 1,
        },
    ]
    if existing:
        patched = await client.patch(
            f"/api/v1/workflows/definitions/{existing['id']}",
            json={"steps": steps_payload},
        )
        assert patched.status_code == 200, patched.text
        wf_id = existing["id"]
    else:
        create_wf = await client.post(
            "/api/v1/workflows/definitions",
            json={
                "name": wf_name,
                "title": "Summary Inject Demo",
                "steps": steps_payload,
            },
        )
        assert create_wf.status_code == 201, create_wf.text
        wf_id = create_wf.json()["id"]

    start = await client.post(
        "/api/v1/workflows/runs",
        json={
            "workflow_definition_id": wf_id,
            "task_prompt": "workflow linear test",
            "workspace_path": "workspace/demo",
        },
    )
    assert start.status_code == 201, start.text
    run_id = start.json()["id"]

    final_status = "pending"
    body = {}
    for _ in range(60):
        await asyncio.sleep(0.5)
        got = await client.get(f"/api/v1/workflows/runs/{run_id}")
        assert got.status_code == 200
        body = got.json()
        final_status = body["status"]
        if final_status in ("completed", "failed", "cancelled"):
            break
    else:
        pytest.fail(f"workflow run timed out, last status={final_status}")

    assert final_status == "completed", body.get("error_message")
    steps = {s["step_key"]: s for s in body["steps"]}
    assert steps["step_a"]["status"] == "completed"
    assert steps["step_b"]["status"] == "completed"
    assert steps["step_a"]["agent_run_id"]
    assert steps["step_b"]["agent_run_id"]
    assert steps["step_a"]["summary"], "step_a should store an output summary"

    b_run = await client.get(f"/api/v1/runs/{steps['step_b']['agent_run_id']}")
    assert b_run.status_code == 200
    prompt = b_run.json()["task_prompt"]
    assert "上游步骤摘要" in prompt
    assert "step_a" in prompt
