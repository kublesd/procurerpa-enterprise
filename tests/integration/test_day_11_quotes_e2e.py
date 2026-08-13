"""Opt-in Day 11 acceptance against a running Compose stack; no mocks are used."""

import os
import uuid
from urllib.parse import urlencode

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("PROCUREMENT_QUOTE_E2E") != "1",
    reason="set PROCUREMENT_QUOTE_E2E=1 with a running stack and two supplier pages",
)


def test_two_supplier_tasks_persist_traceable_quotes() -> None:
    api_url = os.environ["SMOKE_API_URL"].rstrip("/")
    token = os.environ["SMOKE_PLATFORM_ADMIN_TOKEN"]
    organization_id = os.environ["SMOKE_ORGANIZATION_ID"]
    department_id = os.environ["SMOKE_DEPARTMENT_ID"]
    category_id = os.environ["SMOKE_CATEGORY_ID"]
    quote_urls = [url.strip() for url in os.environ["PROCUREMENT_QUOTE_URLS"].split(",") if url.strip()]
    assert len(quote_urls) == 2

    headers = {"Authorization": f"Bearer {token}"}
    task_ids: list[str] = []
    quote_ids: list[str] = []
    for quote_url in quote_urls:
        response = httpx.post(
            f"{api_url}/api/v1/enterprise/procurement/quote-task",
            headers={**headers, "Idempotency-Key": f"day-11-{uuid.uuid4()}"},
            json={
                "organization_id": organization_id,
                "department_id": department_id,
                "category_id": category_id,
                "url": quote_url,
                "risk": {"total_amount_cny": "1000", "supplier_qualified": True},
            },
            timeout=900,
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["outcome"] == "completed"
        assert result["quote_id"]
        assert result["artifact_id"]
        task_ids.append(result["task_id"])
        quote_ids.append(result["quote_id"])

    comparison = httpx.get(
        f"{api_url}/api/v1/enterprise/procurement/quotes/compare?{urlencode([('task_ids', task_id) for task_id in task_ids])}",
        headers=headers,
        timeout=30,
    )
    assert comparison.status_code == 200, comparison.text
    result = comparison.json()
    assert len(result["quotes"]) == 2
    assert result["recommended_quote_id"] in quote_ids
    assert {item["task_id"] for item in result["quotes"]} == set(task_ids)
    assert all(item["artifact_id"] for item in result["quotes"])
