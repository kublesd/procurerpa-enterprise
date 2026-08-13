from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from enterprise.auth.enums import PROCUREMENT_ROLE_MAP
from enterprise.auth.models import TaskExtensionModel
from enterprise.auth.schemas import UserContext
from enterprise.procurement.models import ProcurementCategoryModel
from enterprise.procurement.routes import router
from enterprise.procurement.seed import CATEGORY_GRANTS, DEPARTMENT_ROLES, USERS, seed_procurement_data


def test_category_code_and_task_context_foreign_keys():
    names = {constraint.name for constraint in ProcurementCategoryModel.__table__.constraints}
    assert "uq_org_procurement_category_code" in names
    foreign_keys = {fk.target_fullname for fk in TaskExtensionModel.__table__.foreign_keys}
    assert "tasks.task_id" in foreign_keys
    assert "organizations.organization_id" in foreign_keys
    assert "departments.department_id" in foreign_keys
    assert "procurement_categories.category_id" in foreign_keys


def test_role_mapping():
    assert PROCUREMENT_ROLE_MAP == {
        "super_admin": "platform_admin", "org_admin": "procurement_manager",
        "operator": "procurement_operator", "approver": "procurement_approver", "viewer": "viewer",
    }


@pytest.mark.asyncio
async def test_seed_is_idempotent_when_records_exist():
    session = AsyncMock()
    session.get.return_value = object()
    session.scalar.return_value = "already-present"
    result = await seed_procurement_data(session)
    assert result == {
        "organizations": 1,
        "departments": 2,
        "categories": 2,
        "users": 5,
        "department_roles": 5,
        "category_grants": 4,
    }
    session.add.assert_not_called()


def test_seed_has_minimal_procurement_roles_and_category_scopes():
    assert {user[1] for user in USERS} == {
        "procurement_admin", "it_buyer", "services_buyer", "procurement_approver", "procurement_viewer"
    }
    assert ("eu_it_buyer", "dept_it_procurement", "operator") in DEPARTMENT_ROLES
    assert ("eu_services_buyer", "pc_services") in CATEGORY_GRANTS


def test_context_options_are_scoped_to_current_organization(monkeypatch):
    class Result:
        def __init__(self, rows): self.rows = rows
        def all(self): return self.rows

    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def execute(self, statement):
            text = str(statement)
            assert "organization_id" in text
            if "departments" in text:
                return Result([type("Row", (), {"department_id": "dept_org_a", "department_name": "A", "department_code": "A"})()])
            return Result([type("Row", (), {"category_id": "cat_org_a", "category_name": "A", "category_code": "A"})()])

    app = FastAPI()
    app.include_router(router)
    from enterprise.auth.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: UserContext(user_id="u", org_id="org_a", department_roles=[], business_line_ids=[])
    monkeypatch.setattr("enterprise.procurement.routes.forge_app", SimpleNamespace(DATABASE=SimpleNamespace(Session=lambda: Session())))
    response = TestClient(app).get("/enterprise/procurement/context-options")
    assert response.status_code == 200
    assert response.json()["departments"] == [{"department_id": "dept_org_a", "name": "A", "code": "A"}]
    assert response.json()["categories"] == [{"category_id": "cat_org_a", "name": "A", "code": "A"}]
