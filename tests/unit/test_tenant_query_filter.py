"""Unit tests for procurement tenant SQL filters."""

from sqlalchemy import select

from enterprise.auth.models import TaskExtensionModel
from enterprise.tenant.context import TenantContext
from enterprise.tenant.query_filter import apply_tenant_filter


def _sql(ctx=None) -> str:
    query = apply_tenant_filter(select(TaskExtensionModel), TaskExtensionModel, ctx)
    return str(query.compile(compile_kwargs={"literal_binds": True}))


def test_missing_context_returns_no_data():
    assert "false" in _sql().lower()


def test_admin_is_limited_to_own_organization():
    sql = _sql(TenantContext(org_id="org_1", user_id="admin", has_full_org_visibility=True))
    assert "'org_1'" in sql
    assert "department_id IN" not in sql
    assert "category_id IN" not in sql


def test_restricted_user_must_match_department_and_category():
    sql = _sql(TenantContext(
        org_id="org_1",
        user_id="operator",
        visible_department_ids=["dept_procurement"],
        visible_category_ids=["cat_it"],
    ))
    assert "'org_1'" in sql
    assert "'dept_procurement'" in sql
    assert "'cat_it'" in sql


def test_multiple_categories_are_all_in_the_filter():
    sql = _sql(TenantContext(
        org_id="org_1",
        user_id="operator",
        visible_department_ids=["dept_procurement"],
        visible_category_ids=["cat_it", "cat_services"],
    ))
    assert "'cat_it'" in sql
    assert "'cat_services'" in sql


def test_missing_category_scope_returns_no_data():
    sql = _sql(TenantContext(org_id="org_1", user_id="operator", visible_department_ids=["dept_procurement"]))
    assert "false" in sql.lower()


def test_missing_department_scope_returns_no_data():
    sql = _sql(TenantContext(org_id="org_1", user_id="operator", visible_category_ids=["cat_it"]))
    assert "false" in sql.lower()
