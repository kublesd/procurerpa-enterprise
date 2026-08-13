"""Deterministic procurement dashboard aggregations."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

ACTIVE_STATUSES = {"created", "queued", "running"}
FAILED_STATUSES = {"failed", "timed_out", "terminated"}
FINAL_STATUSES = {"completed", *FAILED_STATUSES, "canceled"}

# Fixed, synthetic procurement model-call facts. They are deliberately kept
# separate from the PostgreSQL task/quote dashboard facts.
DEMO_MODEL_CALLS = (
    {"org_id": "org_procurement_demo", "page_kind": "supplier_catalog", "model_tier": "light", "tokens": 1200, "cache_hit": False},
    {"org_id": "org_procurement_demo", "page_kind": "supplier_catalog", "model_tier": "light", "tokens": 800, "cache_hit": True},
    {"org_id": "org_procurement_demo", "page_kind": "dynamic_quote_portal", "model_tier": "standard", "tokens": 3500, "cache_hit": False},
    {"org_id": "org_procurement_demo", "page_kind": "dynamic_quote_portal", "model_tier": "standard", "tokens": 2500, "cache_hit": True},
    {"org_id": "org_procurement_demo", "page_kind": "erp_contract", "model_tier": "heavy", "tokens": 12000, "cache_hit": False},
    {"org_id": "org_procurement_demo", "page_kind": "erp_contract", "model_tier": "heavy", "tokens": 9000, "cache_hit": True},
)

DEMO_PRICE_PER_1K_USD = {
    "light": Decimal("0.001"),
    "standard": Decimal("0.01"),
    "heavy": Decimal("0.05"),
}


def _status(value) -> str:
    value = getattr(value, "value", value)
    return str(value)


def _category_id(value: str | None) -> str:
    return value or "unassigned"


def compute_procurement_overview(task_rows, quotes, approvals, now: datetime | None = None) -> dict:
    """Compute visible procurement task, quote, and approval totals."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=30)
    final_tasks = [
        (extension, task)
        for extension, task in task_rows
        if extension.created_at >= cutoff and _status(task.status) in FINAL_STATUSES
    ]
    completed = sum(1 for _, task in task_rows if _status(task.status) == "completed")
    failed = sum(1 for _, task in task_rows if _status(task.status) in FAILED_STATUSES)
    final_count = len(final_tasks)

    return {
        "total_tasks": len(task_rows),
        "completed_tasks": completed,
        "active_tasks": sum(1 for _, task in task_rows if _status(task.status) in ACTIVE_STATUSES),
        "failed_tasks": failed,
        "canceled_tasks": sum(1 for _, task in task_rows if _status(task.status) == "canceled"),
        "pending_approvals": sum(1 for approval in approvals if _status(approval.status) == "pending"),
        "total_quotes": len(quotes),
        "success_rate_30d": round(
            sum(1 for _, task in final_tasks if _status(task.status) == "completed") / final_count * 100,
            1,
        )
        if final_count
        else 0.0,
    }


def compute_procurement_trend(task_rows, days: int = 30, now: datetime | None = None) -> list[dict]:
    """Return one completed/failed/total item for each visible calendar day."""
    now = now or datetime.utcnow()
    result = []
    for offset in range(days - 1, -1, -1):
        day = (now - timedelta(days=offset)).date()
        day_rows = [(extension, task) for extension, task in task_rows if extension.created_at.date() == day]
        result.append(
            {
                "date": day.isoformat(),
                "completed": sum(1 for _, task in day_rows if _status(task.status) == "completed"),
                "failed": sum(1 for _, task in day_rows if _status(task.status) in FAILED_STATUSES),
                "total": len(day_rows),
            }
        )
    return result


def compute_category_comparison(task_rows, quotes, category_names: Mapping[str, str]) -> list[dict]:
    """Aggregate unique tasks and quote rows by procurement category."""
    task_groups: dict[str, set[str]] = {}
    completed_groups: dict[str, set[str]] = {}
    quote_counts: dict[str, int] = {}

    for extension, task in task_rows:
        category_id = _category_id(extension.category_id)
        task_groups.setdefault(category_id, set()).add(extension.task_id)
        if _status(task.status) == "completed":
            completed_groups.setdefault(category_id, set()).add(extension.task_id)
    for quote in quotes:
        category_id = _category_id(quote.category_id)
        quote_counts[category_id] = quote_counts.get(category_id, 0) + 1

    category_ids = sorted(set(task_groups) | set(quote_counts))
    result = []
    for category_id in category_ids:
        total_tasks = len(task_groups.get(category_id, set()))
        result.append(
            {
                "category_id": category_id,
                "category_name": category_names.get(category_id, category_id),
                "total_tasks": total_tasks,
                "completed_tasks": len(completed_groups.get(category_id, set())),
                "total_quotes": quote_counts.get(category_id, 0),
                "success_rate": round(
                    len(completed_groups.get(category_id, set())) / total_tasks * 100,
                    1,
                )
                if total_tasks
                else 0.0,
            }
        )
    return result


def build_recent_tasks(task_rows, category_names: Mapping[str, str], limit: int = 10) -> list[dict]:
    """Build the newest visible procurement tasks with stable response fields."""
    rows = sorted(task_rows, key=lambda row: (row[0].created_at, row[1].task_id), reverse=True)[:limit]
    return [
        {
            "task_id": task.task_id,
            "title": task.title,
            "status": _status(task.status),
            "department_id": extension.department_id,
            "category_id": extension.category_id,
            "category_name": category_names.get(extension.category_id, extension.category_id or "unassigned"),
            "risk_level": extension.risk_level,
            "created_at": extension.created_at,
        }
        for extension, task in rows
    ]


def get_demo_model_calls(org_id: str) -> list[dict]:
    """Return fixed synthetic model-call facts for one procurement org."""
    return [dict(call) for call in DEMO_MODEL_CALLS if call["org_id"] == org_id]


def compute_cost_estimation(model_calls, org_id: str) -> dict:
    """Estimate procurement LLM cost and cache savings from demo facts.

    Prices and token counts are illustrative; this is not a real model billing
    or Skyvern action metric.
    """
    org_calls = [
        call for call in model_calls
        if call.get("org_id", call.get("organization_id")) == org_id
    ]
    tier_stats: dict[str, dict[str, int]] = {}
    for call in org_calls:
        raw_tier = call.get("model_tier", "standard")
        tier = getattr(raw_tier, "value", str(raw_tier)).lower()
        stats = tier_stats.setdefault(tier, {"calls": 0, "cached": 0, "tokens": 0})
        stats["calls"] += 1
        try:
            stats["tokens"] += max(0, int(call.get("tokens", 0)))
        except (TypeError, ValueError):
            pass
        stats["cached"] += int(bool(call.get("cache_hit")))

    total_cost = Decimal("0")
    saved_cost = Decimal("0")
    breakdown = []
    for tier, stats in sorted(tier_stats.items()):
        price = DEMO_PRICE_PER_1K_USD.get(tier, DEMO_PRICE_PER_1K_USD["standard"])
        cost = Decimal(stats["tokens"]) / Decimal(1000) * price
        cache_rate = round(stats["cached"] / stats["calls"] * 100, 1) if stats["calls"] else 0.0
        average_tokens = Decimal(stats["tokens"]) / Decimal(stats["calls"] or 1)
        saved = Decimal(stats["cached"]) * average_tokens / Decimal(1000) * price
        total_cost += cost
        saved_cost += saved
        breakdown.append({
            "model_tier": tier,
            "total_calls": stats["calls"],
            "cached_calls": stats["cached"],
            "cache_hit_rate": cache_rate,
            "total_tokens": stats["tokens"],
            "estimated_cost_usd": float(cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
            "estimated_saved_usd": float(saved.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
        })

    return {
        "data_source": "demo_estimate",
        "execution_mode": "simulated",
        "connection_status": "not_connected",
        "total_cost_usd": float(total_cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
        "total_saved_usd": float(saved_cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
        "breakdown": breakdown,
    }


def compute_step_costs(step_rows) -> dict:
    """Aggregate persisted Skyvern Step usage without inventing missing costs."""
    tiers: dict[str, dict] = {}
    for step, task_model in step_rows:
        raw_tier = task_model.get("model_tier") if isinstance(task_model, dict) else None
        tier = raw_tier if raw_tier in {"light", "standard", "heavy"} else "unassigned"
        stats = tiers.setdefault(
            tier,
            {"steps": 0, "input": 0, "output": 0, "cached": 0, "cost": Decimal("0"), "unknown": False},
        )
        input_tokens = max(0, int(step.input_token_count or 0))
        output_tokens = max(0, int(step.output_token_count or 0))
        cached_tokens = max(0, int(step.cached_token_count or 0))
        stats["steps"] += 1
        stats["input"] += input_tokens
        stats["output"] += output_tokens
        stats["cached"] += cached_tokens
        if step.step_cost is None or (Decimal(str(step.step_cost)) == 0 and input_tokens + output_tokens > 0):
            stats["unknown"] = True
        else:
            stats["cost"] += Decimal(str(step.step_cost or 0))

    breakdown = []
    total_input = total_output = total_cached = 0
    total_cost = Decimal("0")
    cost_unknown = False
    for tier, stats in sorted(tiers.items()):
        total_input += stats["input"]
        total_output += stats["output"]
        total_cached += stats["cached"]
        total_cost += stats["cost"]
        cost_unknown |= stats["unknown"]
        breakdown.append(
            {
                "model_tier": tier,
                "total_steps": stats["steps"],
                "input_tokens": stats["input"],
                "output_tokens": stats["output"],
                "cached_tokens": stats["cached"],
                "total_tokens": stats["input"] + stats["output"],
                "cost_usd": None if stats["unknown"] else float(stats["cost"].quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)),
                "cost_status": "unknown" if stats["unknown"] else "known",
            }
        )

    return {
        "data_source": "postgresql_steps",
        "execution_mode": "real",
        "connection_status": "connected",
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cached_tokens": total_cached,
        "total_tokens": total_input + total_output,
        "total_cost_usd": None if cost_unknown else float(total_cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)),
        "cost_status": "unknown" if cost_unknown else "known",
        "breakdown": breakdown,
    }
