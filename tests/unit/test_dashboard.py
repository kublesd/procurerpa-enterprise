"""Unit checks for the database-backed procurement dashboard aggregations."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from enterprise.auth.schemas import DepartmentRole, UserContext
from enterprise.dashboard.routes import _step_cost_statement, router
from enterprise.dashboard.stats import (
    build_recent_tasks,
    compute_category_comparison,
    compute_procurement_overview,
    compute_procurement_trend,
    compute_step_costs,
)

NOW = datetime(2026, 8, 1, 12, 0, 0)


def task_row(task_id: str, status: str, created_at: datetime, category_id: str = "cat_it"):
    extension = SimpleNamespace(
        task_id=task_id,
        created_at=created_at,
        department_id="dept_it",
        category_id=category_id,
        risk_level="low",
    )
    task = SimpleNamespace(task_id=task_id, status=status, title=f"Task {task_id}")
    return extension, task


def quote(quote_id: str, task_id: str, category_id: str = "cat_it"):
    return SimpleNamespace(quote_id=quote_id, task_id=task_id, category_id=category_id)


def approval(status: str):
    return SimpleNamespace(status=status)


def test_overview_counts_statuses_and_only_final_tasks_in_success_rate():
    rows = [
        task_row("completed", "completed", NOW),
        task_row("failed", "failed", NOW),
        task_row("timeout", "timed_out", NOW),
        task_row("canceled", "canceled", NOW),
        task_row("running", "running", NOW),
        task_row("queued", "queued", NOW),
        task_row("old", "completed", NOW - timedelta(days=31)),
    ]
    result = compute_procurement_overview(
        rows,
        [quote("q1", "completed")],
        [approval("pending"), approval("approved")],
        now=NOW,
    )

    assert result == {
        "total_tasks": 7,
        "completed_tasks": 2,
        "active_tasks": 2,
        "failed_tasks": 2,
        "canceled_tasks": 1,
        "pending_approvals": 1,
        "total_quotes": 1,
        "success_rate_30d": 25.0,
    }


def test_trend_counts_timeout_as_failed_and_canceled_only_in_total():
    rows = [
        task_row("completed", "completed", NOW),
        task_row("failed", "failed", NOW),
        task_row("timeout", "timed_out", NOW),
        task_row("canceled", "canceled", NOW),
    ]
    result = compute_procurement_trend(rows, days=1, now=NOW)

    assert result == [{"date": "2026-08-01", "completed": 1, "failed": 2, "total": 4}]


def test_category_counts_unique_tasks_when_one_task_has_multiple_quotes():
    rows = [task_row("task-1", "completed", NOW), task_row("task-1", "completed", NOW)]
    result = compute_category_comparison(
        rows,
        [quote("q1", "task-1"), quote("q2", "task-1")],
        {"cat_it": "IT Equipment"},
    )

    assert result == [{
        "category_id": "cat_it",
        "category_name": "IT Equipment",
        "total_tasks": 1,
        "completed_tasks": 1,
        "total_quotes": 2,
        "success_rate": 100.0,
    }]


def test_recent_tasks_sort_and_limit():
    rows = [
        task_row("old", "completed", NOW - timedelta(days=2)),
        task_row("new", "running", NOW),
        task_row("middle", "failed", NOW - timedelta(days=1)),
    ]

    result = build_recent_tasks(rows, {}, limit=2)

    assert [item["task_id"] for item in result] == ["new", "middle"]


def test_empty_data_returns_zero_and_empty_lists():
    assert compute_procurement_overview([], [], [], now=NOW)["success_rate_30d"] == 0.0
    assert compute_procurement_trend([], days=2, now=NOW) == [
        {"date": "2026-07-31", "completed": 0, "failed": 0, "total": 0},
        {"date": "2026-08-01", "completed": 0, "failed": 0, "total": 0},
    ]
    assert compute_category_comparison([], [], {}) == []
    assert build_recent_tasks([], {}, limit=10) == []
    assert compute_step_costs([]) == {
        "data_source": "postgresql_steps",
        "execution_mode": "real",
        "connection_status": "connected",
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cached_tokens": 0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "cost_status": "known",
        "breakdown": [],
    }


def test_step_costs_use_decimal_and_do_not_invent_missing_provider_cost():
    rows = [
        (SimpleNamespace(input_token_count=100, output_token_count=20, cached_token_count=30, step_cost="0.1234564"), {"model_tier": "light"}),
        (SimpleNamespace(input_token_count=200, output_token_count=40, cached_token_count=0, step_cost=0), {"model_tier": "light"}),
        (SimpleNamespace(input_token_count=50, output_token_count=10, cached_token_count=5, step_cost="0.0000006"), {"model_tier": "standard"}),
    ]

    result = compute_step_costs(rows)

    assert result["total_input_tokens"] == 350
    assert result["total_output_tokens"] == 70
    assert result["total_cached_tokens"] == 35
    assert result["total_tokens"] == 420
    assert result["total_cost_usd"] is None
    assert result["cost_status"] == "unknown"
    assert result["breakdown"] == [
        {
            "model_tier": "light",
            "total_steps": 2,
            "input_tokens": 300,
            "output_tokens": 60,
            "cached_tokens": 30,
            "total_tokens": 360,
            "cost_usd": None,
            "cost_status": "unknown",
        },
        {
            "model_tier": "standard",
            "total_steps": 1,
            "input_tokens": 50,
            "output_tokens": 10,
            "cached_tokens": 5,
            "total_tokens": 60,
            "cost_usd": 0.000001,
            "cost_status": "known",
        },
    ]


def test_step_cost_query_isolates_org_department_and_category_scope():
    user = UserContext(
        user_id="restricted",
        org_id="org_a",
        department_roles=[DepartmentRole(department_id="dept_a", department_name="A", role="operator")],
        procurement_category_ids=["cat_a"],
    )

    compiled = _step_cost_statement(user).compile()
    values = list(compiled.params.values())

    assert "org_a" in values
    assert ["dept_a"] in values
    assert ["cat_a"] in values
    sql = str(compiled)
    assert "tasks.organization_id = steps.organization_id" in sql
    assert "task_extensions.organization_id = tasks.organization_id" in sql

    other_values = list(
        _step_cost_statement(user.model_copy(update={"org_id": "org_b"})).compile().params.values()
    )
    assert "org_b" in other_values
    assert "org_a" not in other_values


def test_dashboard_exposes_only_procurement_endpoints():
    assert {route.path for route in router.routes} == {
        "/enterprise/dashboard/overview",
        "/enterprise/dashboard/trend",
        "/enterprise/dashboard/categories",
        "/enterprise/dashboard/recent-tasks",
        "/enterprise/dashboard/cost",
    }
