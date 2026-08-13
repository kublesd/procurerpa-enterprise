from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException, Response
from starlette.requests import Request

from enterprise.auth.schemas import DepartmentRole, UserContext
from enterprise.procurement import routes
from skyvern.forge.sdk.schemas.tasks import TaskStatus


def _payload() -> routes.QuoteTaskRequest:
    return routes.QuoteTaskRequest(
        organization_id="org_a",
        department_id="dept_a",
        category_id="pc_a",
        url="https://supplier.example/quote",
    )


def _user() -> UserContext:
    return UserContext(
        user_id="user_a",
        org_id="org_a",
        department_roles=[DepartmentRole(department_id="dept_a", department_name="A", role="operator")],
        business_line_ids=[],
        procurement_category_ids=["pc_a"],
    )


@pytest.mark.asyncio
async def test_extracted_quote_is_validated_before_persistence(monkeypatch) -> None:
    added = []
    monkeypatch.setattr(routes, "record_audit_event", AsyncMock())

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def scalar(self, statement):
            sql = str(statement)
            if "task_extensions" in sql:
                return SimpleNamespace(task_id="task_a")
            return "artifact_a"

        def add(self, model):
            added.append(model)

        async def commit(self):
            pass

    monkeypatch.setattr(
        routes,
        "forge_app",
        SimpleNamespace(DATABASE=SimpleNamespace(Session=lambda: Session())),
    )
    task = SimpleNamespace(
        task_id="task_a",
        status=TaskStatus.completed,
        extracted_information={
            "supplier_id": "supplier-a",
            "material_name": "SSD",
            "quantity": "10",
            "unit": "unit",
            "currency": "CNY",
            "unit_price_cny": "10.005",
            "freight_cny": "1.005",
            "moq": "1",
            "delivery_days": 5,
            "confidence": "0.95",
        },
    )

    quote = await routes._persist_extracted_quote(task, _payload(), _user())
    assert quote.task_id == "task_a"
    assert quote.artifact_id == "artifact_a"
    assert quote.unit_price_cny == Decimal("10.01")
    assert len(added) == 1

    task.extracted_information["confidence"] = "0.20"
    with pytest.raises(HTTPException) as error:
        await routes._persist_extracted_quote(task, _payload(), _user())
    assert error.value.status_code == 422
    assert error.value.detail["code"] == "quote_needs_human_confirmation"
    assert len(added) == 2
    assert added[-1].status == "pending"


@pytest.mark.asyncio
async def test_quote_task_uses_native_extraction_request(monkeypatch) -> None:
    user = _user()
    payload = _payload()
    completed = SimpleNamespace(task_id="task_a", status=TaskStatus.completed)
    created_requests = []

    async def create_task(**kwargs):
        created_requests.append(kwargs["task_request"])
        return SimpleNamespace(task_id="task_a", status=TaskStatus.created)

    async def attach(*_args):
        return None

    async def get_task(*_args):
        return completed

    async def persist(*_args):
        return SimpleNamespace(quote_id="sq_a", artifact_id="artifact_a")

    async def validate(*_args):
        pass

    monkeypatch.setattr(routes.settings, "ENV", "local")
    monkeypatch.setattr(routes, "_allowed_smoke_urls", lambda: {payload.url})
    monkeypatch.setattr(routes, "_validate_smoke_context", validate)
    monkeypatch.setattr(routes, "_create_smoke_task", create_task)
    monkeypatch.setattr(routes, "_attach_procurement_context", attach)
    monkeypatch.setattr(routes, "_get_smoke_task", get_task)
    monkeypatch.setattr(routes, "_persist_extracted_quote", persist)
    routes._QUOTE_TASKS.clear()

    request = Request({"type": "http", "method": "POST", "path": "/quote-task", "headers": []})
    result = await routes.quote_task(payload, request, Response(), BackgroundTasks(), "key-a", user)

    assert result.outcome == "completed"
    assert result.quote_id == "sq_a"
    assert created_requests[0].data_extraction_goal == routes._QUOTE_EXTRACTION_GOAL
    assert created_requests[0].extracted_information_schema == routes.QUOTE_EXTRACTION_SCHEMA
