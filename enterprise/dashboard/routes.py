"""Database-backed procurement dashboard routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from enterprise.approval.models import ApprovalRequestModel
from enterprise.auth.dependencies import require_any_operator
from enterprise.auth.models import TaskExtensionModel
from enterprise.auth.schemas import UserContext
from enterprise.procurement.models import ProcurementCategoryModel, SupplierQuoteModel
from enterprise.tenant.context import tenant_context_for
from enterprise.tenant.query_filter import apply_tenant_filter, filter_task_extensions
from skyvern.forge import app as forge_app
from skyvern.forge.sdk.db.models import StepModel, TaskModel

from .stats import (
    build_recent_tasks,
    compute_category_comparison,
    compute_procurement_overview,
    compute_procurement_trend,
    compute_step_costs,
)

router = APIRouter(prefix="/enterprise/dashboard", tags=["dashboard"])


class OverviewResponse(BaseModel):
    total_tasks: int
    completed_tasks: int
    active_tasks: int
    failed_tasks: int
    canceled_tasks: int
    pending_approvals: int
    total_quotes: int
    success_rate_30d: float


class TrendItem(BaseModel):
    date: str
    completed: int
    failed: int
    total: int


class CategoryComparisonItem(BaseModel):
    category_id: str
    category_name: str
    total_tasks: int
    completed_tasks: int
    total_quotes: int
    success_rate: float


class RecentTaskItem(BaseModel):
    task_id: str
    title: str | None
    status: str
    department_id: str
    category_id: str | None
    category_name: str
    risk_level: str
    created_at: datetime


class RecentTasksResponse(BaseModel):
    items: list[RecentTaskItem]


class CostBreakdownItem(BaseModel):
    model_tier: str
    total_steps: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    total_tokens: int
    cost_usd: float | None
    cost_status: str


class CostResponse(BaseModel):
    data_source: str
    execution_mode: str
    connection_status: str
    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    total_tokens: int
    total_cost_usd: float | None
    cost_status: str
    breakdown: list[CostBreakdownItem]


async def _load_dashboard_data(user: UserContext):
    """Load all dashboard facts after applying the caller's procurement scope."""
    scope = tenant_context_for(user)
    task_statement = filter_task_extensions(
        select(TaskExtensionModel, TaskModel).join(
            TaskModel,
            (TaskModel.task_id == TaskExtensionModel.task_id)
            & (TaskModel.organization_id == TaskExtensionModel.organization_id),
        ),
        scope,
    )
    quote_statement = apply_tenant_filter(
        select(SupplierQuoteModel),
        SupplierQuoteModel,
        scope,
    )

    async with forge_app.DATABASE.Session() as session:
        task_rows = (await session.execute(task_statement)).all()
        quotes = (await session.scalars(quote_statement)).all()

        visible_task_ids = {task.task_id for _, task in task_rows}
        approvals = []
        if visible_task_ids:
            approval_statement = select(ApprovalRequestModel).where(
                ApprovalRequestModel.organization_id == user.org_id,
                ApprovalRequestModel.task_id.in_(visible_task_ids),
            )
            approvals = (await session.scalars(approval_statement)).all()

        category_ids = {
            extension.category_id
            for extension, _ in task_rows
            if extension.category_id
        }
        category_ids.update(quote.category_id for quote in quotes if quote.category_id)
        category_names = {}
        if category_ids:
            category_rows = await session.execute(
                select(
                    ProcurementCategoryModel.category_id,
                    ProcurementCategoryModel.category_name,
                ).where(
                    ProcurementCategoryModel.organization_id == user.org_id,
                    ProcurementCategoryModel.category_id.in_(category_ids),
                )
            )
            category_names = {
                row.category_id: row.category_name
                for row in category_rows
            }

    return task_rows, quotes, approvals, category_names


def _step_cost_statement(user: UserContext):
    scope = tenant_context_for(user)
    return filter_task_extensions(
        select(StepModel, TaskModel.model)
        .join(
            TaskModel,
            (TaskModel.task_id == StepModel.task_id)
            & (TaskModel.organization_id == StepModel.organization_id),
        )
        .join(
            TaskExtensionModel,
            (TaskExtensionModel.task_id == TaskModel.task_id)
            & (TaskExtensionModel.organization_id == TaskModel.organization_id),
        ),
        scope,
    )


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(user: UserContext = Depends(require_any_operator)):
    task_rows, quotes, approvals, _ = await _load_dashboard_data(user)
    return compute_procurement_overview(task_rows, quotes, approvals)


@router.get("/trend", response_model=list[TrendItem])
async def get_trend(
    user: UserContext = Depends(require_any_operator),
    days: int = Query(30, ge=1, le=90),
):
    task_rows, _, _, _ = await _load_dashboard_data(user)
    return compute_procurement_trend(task_rows, days=days)


@router.get("/categories", response_model=list[CategoryComparisonItem])
async def get_categories(user: UserContext = Depends(require_any_operator)):
    task_rows, quotes, _, category_names = await _load_dashboard_data(user)
    return compute_category_comparison(task_rows, quotes, category_names)


@router.get("/recent-tasks", response_model=RecentTasksResponse)
async def get_recent_tasks(
    user: UserContext = Depends(require_any_operator),
    limit: int = Query(10, ge=1, le=50),
):
    task_rows, _, _, category_names = await _load_dashboard_data(user)
    return {"items": build_recent_tasks(task_rows, category_names, limit=limit)}


@router.get("/cost", response_model=CostResponse)
async def get_cost_estimation(
    user: UserContext = Depends(require_any_operator),
) -> CostResponse:
    """Return real token and provider-cost facts for visible procurement steps."""
    async with forge_app.DATABASE.Session() as session:
        rows = (await session.execute(_step_cost_statement(user))).all()
    result = compute_step_costs(rows)
    return CostResponse(**result)
