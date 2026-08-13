"""Explicit procurement scope filters for SQLAlchemy selects."""

from sqlalchemy import false

from enterprise.auth.models import TaskExtensionModel

from .context import get_tenant_context


def apply_tenant_filter(query, model_class: type, ctx=None):
    """Constrain a procurement query to the supplied trusted tenant scope."""
    ctx = ctx or get_tenant_context()
    if ctx is None:
        return query.where(false())

    query = query.where(model_class.organization_id == ctx.org_id)
    if ctx.has_full_org_visibility:
        return query
    if not ctx.visible_department_ids or not ctx.visible_category_ids:
        return query.where(false())
    return query.where(
        model_class.department_id.in_(ctx.visible_department_ids),
        model_class.category_id.in_(ctx.visible_category_ids),
    )


def filter_task_extensions(query, ctx=None):
    return apply_tenant_filter(query, TaskExtensionModel, ctx)
