from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from enterprise.auth.jwt_service import create_enterprise_token
from enterprise.auth.schemas import DepartmentRole, UserContext
from enterprise.procurement import routes
from enterprise.procurement.routes import router
from skyvern.config import Settings, settings
from skyvern.forge.sdk.schemas.tasks import TaskRequest, TaskStatus
from skyvern.services import task_v1_service

SMOKE_PATH = "/api/v1/enterprise/procurement/smoke-task"
PAYLOAD = {
    "organization_id": "org-smoke",
    "department_id": "dept-smoke",
    "category_id": "cat-smoke",
    "url": "https://example.com/",
    "risk": {
        "total_amount_cny": "100000",
        "supplier_id": "supplier-smoke",
        "supplier_qualified": True,
        "selected_quote_cny": "100",
        "average_quote_cny": "100",
        "operation_type": "standard",
        "tax_rate": "0.13",
        "redacted_description": "Allowlisted smoke procurement",
    },
}


def _token(role: str, organization_id: str = "org-smoke") -> str:
    return create_enterprise_token(
        user_id="user-smoke",
        org_id=organization_id,
        department_roles=[DepartmentRole(department_id="dept-smoke", department_name="Smoke", role=role)],
        business_line_ids=[],
    )


def _user(role: str = "operator", organization_id: str = "org-smoke") -> UserContext:
    return UserContext(
        user_id="user-smoke",
        org_id=organization_id,
        department_roles=[DepartmentRole(department_id="dept-smoke", department_name="Smoke", role=role)],
        business_line_ids=[],
        procurement_category_ids=["cat-smoke"],
    )


def _client(user: UserContext | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    if user is not None:
        from enterprise.auth.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _headers(role: str = "super_admin", key: str = "smoke-key") -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(role)}", "Idempotency-Key": key}


def test_smoke_task_requires_authentication_and_procurement_role(monkeypatch) -> None:
    client = _client()

    assert client.post(SMOKE_PATH, json=PAYLOAD, headers={"Idempotency-Key": "missing-auth"}).status_code == 401

    async def load_viewer(_user_id: str) -> UserContext:
        return _user("viewer")

    monkeypatch.setattr("enterprise.auth.dependencies._load_current_user", load_viewer)
    assert client.post(SMOKE_PATH, json=PAYLOAD, headers=_headers("super_admin", "viewer-role")).status_code == 403


def test_smoke_task_rejects_non_development_wrong_org_and_unallowlisted_url(monkeypatch) -> None:
    client = _client(_user())

    monkeypatch.setattr(settings, "ENV", "production")
    assert client.post(SMOKE_PATH, json=PAYLOAD, headers=_headers(key="production")).status_code == 404

    monkeypatch.setattr(settings, "ENV", "local")
    wrong_org = {**PAYLOAD, "organization_id": "other-org"}
    assert client.post(SMOKE_PATH, json=wrong_org, headers=_headers(key="wrong-org")).status_code == 403

    bad_url = {**PAYLOAD, "url": "https://not-allowlisted.invalid/"}
    assert client.post(SMOKE_PATH, json=bad_url, headers=_headers(key="bad-url")).status_code == 400


def test_smoke_task_is_idempotent_and_reports_execution_failure(monkeypatch) -> None:
    calls = 0
    create_options = []
    notifications = []

    async def create_task(**kwargs):
        nonlocal calls
        calls += 1
        create_options.append(kwargs)
        return SimpleNamespace(task_id="task-smoke", status=TaskStatus.created)

    async def created_task(*_args, **_kwargs):
        return SimpleNamespace(task_id="task-smoke", status=TaskStatus.created)

    monkeypatch.setattr(routes, "_create_smoke_task", create_task)
    monkeypatch.setattr(routes, "_get_smoke_task", created_task)
    async def validate_context(*_args):
        pass

    monkeypatch.setattr(routes, "_validate_smoke_context", validate_context)
    attached = []

    async def attach_context(*args):
        attached.append(args)
        return "apr-smoke"

    monkeypatch.setattr(routes, "_attach_procurement_context", attach_context)

    async def notify(context):
        notifications.append(context)

    monkeypatch.setattr(routes, "notify_approval_created", notify)
    client = _client(_user())

    first = client.post(SMOKE_PATH, json=PAYLOAD, headers=_headers(key="same-key"))
    second = client.post(SMOKE_PATH, json=PAYLOAD, headers=_headers(key="same-key"))

    assert first.status_code == 202
    assert first.json()["task_id"] == "task-smoke"
    assert first.json()["outcome"] == "pending_approval"
    assert first.json()["approval_id"] == "apr-smoke"
    assert second.status_code == 202
    assert second.json()["idempotent"] is True
    assert calls == 1
    assert len(attached) == 1
    assert len(notifications) == 1
    assert notifications[0].approval_id == "apr-smoke"
    assert not hasattr(notifications[0], "operation_description")
    assert attached[0][3].risk_level == "high"
    assert create_options[0]["defer_execution"] is True

    async def failed_task(*_args, **_kwargs):
        return SimpleNamespace(task_id="task-failed", status=TaskStatus.failed)

    async def attach_without_approval(*_args):
        return None

    monkeypatch.setattr(routes, "_attach_procurement_context", attach_without_approval)
    monkeypatch.setattr(routes, "_get_smoke_task", failed_task)
    failed = client.post(SMOKE_PATH, json=PAYLOAD, headers=_headers(key="failed-key"))
    assert failed.status_code == 502
    assert failed.json()["outcome"] == "failed"


def test_smoke_task_reports_creation_failure(monkeypatch) -> None:
    async def fail_create(**_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(routes, "_create_smoke_task", fail_create)
    async def validate_context(*_args):
        pass

    monkeypatch.setattr(routes, "_validate_smoke_context", validate_context)
    response = _client(_user()).post(SMOKE_PATH, json=PAYLOAD, headers=_headers(key="creation-failure"))

    assert response.status_code == 503
    assert response.json()["detail"] == "Smoke task could not be created by Skyvern"


def test_smoke_task_rejects_ungranted_department_or_category() -> None:
    user = _user()
    user.procurement_category_ids = ["cat-granted"]
    response = _client(user).post(
        SMOKE_PATH,
        json={**PAYLOAD, "category_id": "cat-other"},
        headers=_headers(key="outside-scope"),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_smoke_task_persists_procurement_context(monkeypatch) -> None:
    saved = []
    audit = AsyncMock()

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def add(self, model):
            saved.append(model)

        async def commit(self):
            pass

    monkeypatch.setattr(routes, "forge_app", SimpleNamespace(DATABASE=SimpleNamespace(Session=lambda: Session())))
    monkeypatch.setattr(routes, "record_audit_event", audit)
    payload = routes.SmokeTaskRequest(**PAYLOAD)
    risk = await routes.detect_risk(payload.risk.to_context())
    await routes._attach_procurement_context("task-smoke", payload, _user(), risk)
    assert (saved[0].task_id, saved[0].department_id, saved[0].category_id) == (
        "task-smoke", "dept-smoke", "cat-smoke"
    )
    assert saved[0].risk_level == "high"
    assert saved[0].risk_result["deterministic_level"] == "high"
    assert saved[1].requester_user_id == "user-smoke"
    assert saved[1].approver_department_id == "dept-smoke"
    assert saved[1].status == "pending"
    assert saved[1].timeout_seconds == 3600
    assert [call.kwargs["action_type"] for call in audit.await_args_list] == [
        "risk_assessed",
        "procurement_submitted",
        "approval_requested",
    ]

    saved.clear()
    audit.reset_mock()
    low_payload = routes.SmokeTaskRequest(**{
        **PAYLOAD,
        "risk": {**PAYLOAD["risk"], "total_amount_cny": "1000"},
    })
    low_risk = await routes.detect_risk(low_payload.risk.to_context())
    assert await routes._attach_procurement_context("task-low", low_payload, _user(), low_risk) is None
    assert len(saved) == 1
    assert [call.kwargs["action_type"] for call in audit.await_args_list] == [
        "risk_assessed",
        "procurement_submitted",
    ]


@pytest.mark.asyncio
async def test_skyvern_task_creation_can_defer_execution(monkeypatch) -> None:
    executed = []
    task_number = 0

    class Agent:
        async def create_task(self, _task, _organization_id):
            nonlocal task_number
            task_number += 1
            return SimpleNamespace(task_id=f"task-{task_number}")

    class Database:
        async def create_task_run(self, **_kwargs):
            pass

    class Executor:
        async def execute_task(self, **kwargs):
            executed.append(kwargs["task_id"])

    monkeypatch.setattr(task_v1_service, "app", SimpleNamespace(agent=Agent(), DATABASE=Database()))
    monkeypatch.setattr(
        task_v1_service.AsyncExecutorFactory,
        "get_executor",
        staticmethod(lambda: Executor()),
    )
    request = TaskRequest(url="https://example.com/", navigation_goal="Smoke")
    organization = SimpleNamespace(organization_id="org-smoke")

    await task_v1_service.run_task(request, organization, defer_execution=True)
    await task_v1_service.run_task(request, organization)

    assert executed == ["task-2"]


@pytest.mark.parametrize("secret", ["", "PLACEHOLDER", "dev-only-change-before-sharing", "change-me"])
def test_non_development_rejects_placeholder_secret(secret: str) -> None:
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings(ENV="production", SECRET_KEY=secret).validate_runtime_security()

    Settings(ENV="local", SECRET_KEY=secret).validate_runtime_security()
