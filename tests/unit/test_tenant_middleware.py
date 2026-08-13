"""Unit tests for trusted tenant middleware scope construction."""

import pytest
from fastapi import Response
from starlette.requests import Request

from enterprise.auth.jwt_service import create_enterprise_token
from enterprise.auth.schemas import DepartmentRole, UserContext
from enterprise.tenant.context import get_tenant_context, tenant_context_for
from enterprise.tenant.middleware import TenantIsolationMiddleware, _is_whitelisted


def _user(role="operator", categories=None, cross_read=False) -> UserContext:
    return UserContext(
        user_id="eu_test",
        org_id="org_procurement_demo",
        department_roles=[DepartmentRole(department_id="dept_it_procurement", department_name="IT Procurement", role=role)],
        business_line_ids=[],
        procurement_category_ids=categories or ["pc_it"],
        has_cross_org_read=cross_read,
    )


class TestWhitelist:
    def test_login_route_whitelisted(self):
        assert _is_whitelisted("/api/v1/enterprise/auth/login") is True

    def test_health_route_whitelisted(self):
        assert _is_whitelisted("/health") is True

    def test_task_route_not_whitelisted(self):
        assert _is_whitelisted("/api/v1/enterprise/procurement/tasks") is False


def test_admin_has_full_own_organization_visibility():
    ctx = tenant_context_for(_user("org_admin", categories=[]))
    assert ctx.has_full_org_visibility is True
    assert ctx.org_id == "org_procurement_demo"


def test_cross_org_read_is_full_visibility_within_own_organization():
    ctx = tenant_context_for(_user("viewer", categories=[], cross_read=True))
    assert ctx.has_full_org_visibility is True
    assert ctx.org_id == "org_procurement_demo"


def test_operator_keeps_multiple_granted_categories():
    ctx = tenant_context_for(_user(categories=["pc_it", "pc_services"]))
    assert ctx.visible_category_ids == ["pc_it", "pc_services"]
    assert ctx.is_restricted is True


@pytest.mark.asyncio
async def test_middleware_uses_server_scope_not_forged_jwt_scope(monkeypatch):
    token = create_enterprise_token(
        user_id="eu_test",
        org_id="forged_org",
        department_roles=[DepartmentRole(department_id="forged_dept", department_name="Forged", role="org_admin")],
        business_line_ids=[],
    )

    async def load_user(_user_id):
        return _user(categories=["pc_it"])

    observed = None

    async def endpoint(_request):
        nonlocal observed
        observed = get_tenant_context()
        return Response()

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/v1/enterprise/procurement/tasks",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
        "query_string": b"",
    })
    monkeypatch.setattr("enterprise.tenant.middleware._load_current_user", load_user)
    await TenantIsolationMiddleware(None).dispatch(request, endpoint)

    assert observed.org_id == "org_procurement_demo"
    assert observed.visible_department_ids == ["dept_it_procurement"]
    assert observed.visible_category_ids == ["pc_it"]
    assert observed.has_full_org_visibility is False
    assert get_tenant_context() is None
