"""Day 4 procurement task visibility checks."""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from enterprise.auth.dependencies import get_current_user
from enterprise.auth.schemas import DepartmentRole, UserContext
from enterprise.procurement.routes import router


def _user(user_id="eu_it_buyer", org_id="org_procurement_demo", department_id="dept_it_procurement", category_ids=None, role="operator"):
    return UserContext(
        user_id=user_id,
        org_id=org_id,
        department_roles=[DepartmentRole(department_id=department_id, department_name=department_id, role=role)],
        business_line_ids=[],
        procurement_category_ids=category_ids or ["pc_it"],
    )


def _row(task_id, org_id, department_id, category_id):
    return (
        SimpleNamespace(
            task_id=task_id,
            organization_id=org_id,
            department_id=department_id,
            category_id=category_id,
            risk_level="low",
            risk_reason="No procurement risk indicators detected",
            risk_result={"deterministic_level": "low"},
            created_by="eu_proc_admin",
        ),
        SimpleNamespace(task_id=task_id, title=task_id, status="completed"),
    )


TASKS = (
    _row("task_it", "org_procurement_demo", "dept_it_procurement", "pc_it"),
    _row("task_services", "org_procurement_demo", "dept_services_procurement", "pc_services"),
    _row("task_it_services", "org_procurement_demo", "dept_it_procurement", "pc_services"),
    _row("task_other_org", "org_other", "dept_it_procurement", "pc_it"),
)


def _client(monkeypatch, user):
    class Result:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

        def one_or_none(self):
            return self.rows[0] if self.rows else None

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def execute(self, statement):
            sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
            assert "JOIN tasks" in sql
            assert f"'{user.org_id}'" in sql
            is_admin = user.is_org_admin or user.has_cross_org_read
            if not is_admin:
                assert f"'{user.department_ids[0]}'" in sql
                for category_id in user.procurement_category_ids:
                    assert f"'{category_id}'" in sql
            rows = [
                row for row in TASKS
                if row[0].organization_id == user.org_id
                and (is_admin or (
                    row[0].department_id in user.department_ids
                    and row[0].category_id in user.procurement_category_ids
                ))
            ]
            if "task_extensions.task_id =" in sql:
                rows = [row for row in rows if f"'{row[0].task_id}'" in sql]
            return Result(rows)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(
        "enterprise.procurement.routes.forge_app",
        SimpleNamespace(DATABASE=SimpleNamespace(Session=lambda: Session())),
    )
    return TestClient(app)


def _task_ids(response):
    return [task["task_id"] for task in response.json()["tasks"]]


def test_task_with_written_procurement_context_is_visible(monkeypatch):
    response = _client(monkeypatch, _user()).get("/enterprise/procurement/tasks")
    assert response.status_code == 200
    assert _task_ids(response) == ["task_it"]


def test_different_department_and_category_tasks_are_not_visible(monkeypatch):
    response = _client(monkeypatch, _user()).get("/enterprise/procurement/tasks")
    assert "task_services" not in _task_ids(response)
    assert "task_it_services" not in _task_ids(response)


def test_different_organization_task_is_not_visible(monkeypatch):
    response = _client(monkeypatch, _user()).get("/enterprise/procurement/tasks")
    assert "task_other_org" not in _task_ids(response)


def test_admin_sees_only_own_organization_tasks(monkeypatch):
    response = _client(monkeypatch, _user(user_id="eu_proc_admin", category_ids=[], role="org_admin")).get(
        "/enterprise/procurement/tasks"
    )
    assert response.status_code == 200
    assert _task_ids(response) == ["task_it", "task_services", "task_it_services"]


def test_out_of_scope_task_detail_is_not_disclosed(monkeypatch):
    response = _client(monkeypatch, _user()).get("/enterprise/procurement/tasks/task_services")
    assert response.status_code == 404
