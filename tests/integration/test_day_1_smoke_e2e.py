"""Opt-in smoke acceptance against a running Compose stack; no mocks are used."""

import asyncio
import os
import uuid

import asyncpg
import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("PROCUREMENT_SMOKE_E2E") != "1",
    reason="set PROCUREMENT_SMOKE_E2E=1 with a running stack and platform-admin token",
)


def test_smoke_task_persists_task_step_and_action() -> None:
    api_url = os.environ["SMOKE_API_URL"].rstrip("/")
    token = os.environ["SMOKE_PLATFORM_ADMIN_TOKEN"]
    organization_id = os.environ["SMOKE_ORGANIZATION_ID"]
    department_id = os.environ["SMOKE_DEPARTMENT_ID"]
    category_id = os.environ["SMOKE_CATEGORY_ID"]
    database_url = os.environ["SMOKE_DATABASE_URL"]

    response = httpx.post(
        f"{api_url}/api/v1/enterprise/procurement/smoke-task",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"e2e-{uuid.uuid4()}"},
        json={
            "organization_id": organization_id,
            "department_id": department_id,
            "category_id": category_id,
            "url": "https://example.com/",
        },
        timeout=180,
    )
    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]
    assert response.json()["outcome"] == "completed"

    async def verify() -> None:
        connection = await asyncpg.connect(database_url)
        try:
            task = await connection.fetchrow(
                "SELECT task_id FROM tasks WHERE task_id = $1 AND organization_id = $2", task_id, organization_id
            )
            steps = await connection.fetch(
                "SELECT step_id FROM steps WHERE task_id = $1 AND organization_id = $2", task_id, organization_id
            )
            actions = await connection.fetch("SELECT action_id FROM actions WHERE task_id = $1", task_id)
        finally:
            await connection.close()
        assert task is not None
        assert steps
        assert actions

    asyncio.run(verify())
