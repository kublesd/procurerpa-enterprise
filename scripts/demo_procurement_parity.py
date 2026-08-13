"""Run the first-phase ProcureRPA parity demo.

The entry point composes existing procurement helpers with synthetic input. It
does not create a Skyvern Task, call a real model, or write business data.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

from pydantic import BaseModel

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from enterprise.agent.coordinator import AgentCoordinator
from enterprise.agent.executor import ExecutorAgent
from enterprise.agent.planner import PlannerAgent
from enterprise.approval.routing import route_approval
from enterprise.auth.permission import resolve_permission
from enterprise.auth.schemas import DepartmentRole, UserContext
from enterprise.approval.risk_keywords import (
    RISK_ORDER,
    amount_risk_from_text,
    find_procurement_risk_keywords,
)
from enterprise.dashboard.stats import DEMO_MODEL_CALLS, compute_cost_estimation
from enterprise.llm.action_cache import (
    ActionCacheStore,
    cache_action_decision,
    configure_cache_store,
    get_cache_store,
    lookup_cached_decision,
)
from enterprise.llm.human_intervention import (
    HumanResolution,
    ResolutionAction,
    StuckTaskInfo,
    resolve_stuck_task,
)
from enterprise.llm.model_router import ProcurementPageKind, route_procurement_page
from enterprise.llm.resilient_caller import build_structured_prompt, call_llm_with_retry
from enterprise.llm.task_states import validate_transition
from enterprise.skills.executor import execute_pipeline
from enterprise.workflows.templates import PURCHASE_ORDER_DUE, build_skill_pipeline

# Importing the package registers the seven built-in procurement skills.
import enterprise.skills  # noqa: F401,E402


DEMO_ORG_ID = "org_procurement_demo"
DEMO_TASK_ID = "task_p6_procurement_demo"
DEMO_GOAL = "为 IT 部门采购 500 把办公椅"
DEMO_LABELS = {
    "data_source": "synthetic_demo",
    "execution_mode": "simulated",
    "connection_status": "not_connected",
}


class ProcurementPageAction(BaseModel):
    """Small synthetic schema used to show the P2 JSON path."""

    action: str
    target: str
    supplier_name: str
    confidence: float


def _run_risk_and_approval() -> dict:
    description = "大额采购，供应商资质需复核，金额 12 万元"
    matched = find_procurement_risk_keywords(description)
    text_amount = amount_risk_from_text(description)
    levels = [item.risk_level for item in matched]
    if text_amount:
        levels.append(text_amount[1])
    risk_level = max(levels, key=RISK_ORDER.get, default="low")

    department_id = "dept_it_procurement"
    category_id = "pc-it"
    route = route_approval(
        risk_level,
        department_id,
        procurement_category_id=category_id,
    )
    approver = UserContext(
        user_id="procurement_approver_demo",
        org_id=DEMO_ORG_ID,
        department_roles=[
            DepartmentRole(
                department_id=department_id,
                department_name="IT Procurement",
                role="approver",
            ),
        ],
        procurement_category_ids=[category_id],
    )

    return {
        "status": "pending_approval" if route.requires_approval else "ready",
        "risk_level": risk_level,
        "risk_stage": "deterministic_rules",
        "matched_keywords": [item.keyword for item in matched],
        "approval_route": {
            "requires_approval": route.requires_approval,
            "approver_department_id": route.approver_department_id,
            "approver_category_id": route.approver_category_id,
        },
        "approver_permission": resolve_permission(
            approver,
            DEMO_ORG_ID,
            department_id,
            resource_category_id=category_id,
        ).value,
        **DEMO_LABELS,
    }


async def _run_llm_resilience() -> dict:
    responses = iter(
        [
            "not-json",
            '```json\n{"action":"open_quote","target":"quote-link",'
            '"supplier_name":"Synthetic Supplier","confidence":0.92}\n```',
        ]
    )

    async def flaky_llm(_prompt: str) -> str:
        return next(responses)

    prompt = build_structured_prompt(
        "从供应商询价页提取报价动作",
        ProcurementPageAction,
    )
    parsed = await call_llm_with_retry(
        flaky_llm,
        prompt,
        ProcurementPageAction,
        max_retries=2,
        retry_delays=[0, 0],
    )

    async def unavailable_llm(_prompt: str) -> str:
        raise TimeoutError

    failed = await call_llm_with_retry(
        unavailable_llm,
        prompt,
        ProcurementPageAction,
        max_retries=2,
        retry_delays=[0, 0],
    )
    stuck_task = StuckTaskInfo(
        task_id=DEMO_TASK_ID,
        org_id=DEMO_ORG_ID,
        department_id="dept_it_procurement",
        stuck_action_index=2,
        stuck_action_type="quote_extract",
        page_url="https://supplier.example/quotes",
        screenshot_key="demo/p6/quote-page.png",
        llm_errors=failed.errors,
        llm_raw_response=None,
        stuck_since="2026-08-02T00:00:00",
        total_actions=5,
        completed_actions=2,
    )
    resolution = resolve_stuck_task(
        stuck_task,
        HumanResolution(
            task_id=DEMO_TASK_ID,
            action=ResolutionAction.MANUAL_COMPLETE,
            resolved_by="procurement_operator_demo",
            manual_result={"quote_reference": "quote-demo-001"},
        ),
    )

    return {
        "structured_json": {
            "success": parsed.success,
            "attempts": parsed.attempts,
            "parsed": parsed.data is not None,
        },
        "needs_human": {
            "status": "needs_human" if failed.needs_human else "failed",
            "attempts": failed.attempts,
            "resolution": resolution["resolution"],
            "new_status": resolution["new_status"],
            "transition_valid": validate_transition("running", "needs_human"),
        },
        **DEMO_LABELS,
    }


async def _run_planner_and_executor() -> dict:
    state = await AgentCoordinator(
        planner=PlannerAgent(),
        executor=ExecutorAgent(),
    ).run(
        task_id=DEMO_TASK_ID,
        org_id=DEMO_ORG_ID,
        navigation_goal=DEMO_GOAL,
    )
    plan = state.current_plan
    if plan is None:
        raise RuntimeError("procurement demo plan was not created")

    return {
        "status": state.status,
        "subtask_count": len(plan.subtasks),
        "completed_subtasks": len(state.completed_subtasks),
        "all_steps_simulated": all(
            (subtask.result_data or {}).get("simulated") is True
            for subtask in plan.subtasks
        ),
        "steps": [subtask.goal for subtask in plan.subtasks],
        **DEMO_LABELS,
    }


async def _run_skill_pipeline() -> dict:
    steps = build_skill_pipeline(
        PURCHASE_ORDER_DUE,
        {
            "purchase_portal_url": "https://procurement.example.com",
            "username": "buyer-demo",
            "password": "demo-only",
            "days_ahead": "7",
        },
    )
    page = AsyncMock(name="fake_procurement_page")
    page.query_selector.return_value = object()
    page.evaluate.return_value = {
        "headers": ["订单号", "交期", "状态"],
        "rows": [["PO-DEMO-001", "2026-08-15", "待交付"]],
    }

    async def fake_page_llm(_page, _goal: str) -> None:
        return None

    result = await execute_pipeline(
        steps,
        context={"page": page, "llm_handler": fake_page_llm},
    )
    return {
        "template_id": PURCHASE_ORDER_DUE.template_id,
        "steps": [step.skill_name for step in steps],
        "success": result.success,
        "steps_completed": result.steps_completed,
        "fake_page": True,
        "execution_mode": result.execution_mode,
        "connection_status": "not_connected",
    }


def _run_model_cache_and_cost() -> dict:
    previous_store = get_cache_store()
    store = ActionCacheStore()
    configure_cache_store(store)
    try:
        dom = '<div class="quote-page" data-reactid="demo-123"><button>询价</button></div>'
        changed_dom = "<div><button>询价</button><span>新字段</span></div>"
        goal = "打开供应商询价页面"
        initial_miss = lookup_cached_decision(DEMO_ORG_ID, dom, goal) is None
        cache_action_decision(
            DEMO_ORG_ID,
            dom,
            goal,
            {"action": "open_quote", "execution_mode": "simulated"},
        )
        cache_hit = lookup_cached_decision(DEMO_ORG_ID, dom, goal) is not None
        changed_dom_miss = lookup_cached_decision(DEMO_ORG_ID, changed_dom, goal) is None

        routing = {}
        for page_kind in ProcurementPageKind:
            decision = route_procurement_page(page_kind)
            routing[page_kind.value] = {
                "complexity": decision.complexity.value,
                "model_tier": decision.model_tier.value,
            }

        return {
            "model_routing": routing,
            "cache": {
                "initial_miss": initial_miss,
                "same_page_hit": cache_hit,
                "changed_dom_miss": changed_dom_miss,
                "stats": dict(store.stats),
                **DEMO_LABELS,
            },
            "cost": compute_cost_estimation(DEMO_MODEL_CALLS, DEMO_ORG_ID),
        }
    finally:
        configure_cache_store(previous_store)


async def run_demo() -> dict:
    """Return one safe, JSON-serializable P1-P5 procurement demo result."""
    risk = _run_risk_and_approval()
    resilience = await _run_llm_resilience()
    planner = await _run_planner_and_executor()
    pipeline = await _run_skill_pipeline()
    model_cache_cost = _run_model_cache_and_cost()

    return {
        "demo": {
            "task_id": DEMO_TASK_ID,
            "goal": DEMO_GOAL,
            "labels": ["demo", "simulated", "not_connected"],
        },
        "p1_risk_approval": risk,
        "p2_llm_resilience": resilience,
        "p3_planner_executor": planner,
        "p4_skill_pipeline": pipeline,
        "p5_model_cache_cost": model_cache_cost,
        "demo_audit_summary": {
            "event_types": [
                "risk_assessed",
                "approval_routed",
                "plan_completed",
                "human_resolution_applied",
                "action_cache_hit",
            ],
            "approval_status": risk["status"],
            "plan_status": planner["status"],
            "human_resolution": resilience["needs_human"]["resolution"],
            "cache_hit": model_cache_cost["cache"]["same_page_hit"],
            "persistence": "not_connected",
            **DEMO_LABELS,
        },
        "real_procurement_main_chain": {
            "status": "preserved",
            "execution_mode": "real",
            "connection_status": "not_invoked_by_this_demo",
            "route": (
                "procurement/quote-task -> Skyvern Task/Artifact -> "
                "SupplierQuote -> Decimal comparison -> approval/audit/Dashboard"
            ),
            "verification": "existing baseline is unchanged; this entry does not replace it",
        },
    }


def main() -> None:
    print(json.dumps(asyncio.run(run_demo()), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
