"""P5 acceptance checks for procurement routing, cache, and demo costs."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from enterprise.auth.schemas import DepartmentRole, UserContext
from enterprise.dashboard.stats import DEMO_MODEL_CALLS, compute_cost_estimation
from enterprise.llm.action_cache import (
    ActionCacheStore,
    cache_action_decision,
    configure_cache_store,
    lookup_cached_decision,
)
from enterprise.llm.model_router import (
    ComplexityLevel,
    ModelTier,
    ProcurementPageKind,
    route_procurement_page,
)


class TestP5ProcurementAlignment(unittest.TestCase):
    def test_three_procurement_page_profiles_route_to_fixed_tiers(self):
        expected = {
            ProcurementPageKind.SUPPLIER_CATALOG: (ComplexityLevel.SIMPLE, ModelTier.LIGHT),
            ProcurementPageKind.DYNAMIC_QUOTE_PORTAL: (ComplexityLevel.MODERATE, ModelTier.STANDARD),
            ProcurementPageKind.ERP_CONTRACT: (ComplexityLevel.COMPLEX, ModelTier.HEAVY),
        }
        for page_kind, (complexity, tier) in expected.items():
            decision = route_procurement_page(page_kind)
            assert (decision.complexity, decision.model_tier) == (complexity, tier)
            assert decision.data_source == "demo_estimate"
            assert decision.execution_mode == "simulated"
            assert decision.connection_status == "not_connected"

    def test_action_cache_hits_same_org_dom_and_goal_only(self):
        store = ActionCacheStore()
        configure_cache_store(store)
        dom = '<div class="quote-page" data-reactid="abc123"><button>询价</button></div>'
        changed_dynamic_dom = '<div class="other-class" data-reactid="xyz789"><button>询价</button></div>'
        goal = "打开供应商询价页面"

        assert lookup_cached_decision("org_procurement_demo", dom, goal) is None
        cache_action_decision(
            "org_procurement_demo",
            dom,
            goal,
            {"action": "open_quote", "execution_mode": "simulated"},
        )
        assert lookup_cached_decision("org_procurement_demo", changed_dynamic_dom, goal) is not None
        assert lookup_cached_decision("org_procurement_demo", dom, "提取报价") is None
        assert lookup_cached_decision("other_org", dom, goal) is None
        assert store.stats["execution_mode"] == "simulated"

    def test_fixed_procurement_demo_costs_are_repeatable_and_labeled(self):
        first = compute_cost_estimation(DEMO_MODEL_CALLS, "org_procurement_demo")
        second = compute_cost_estimation(DEMO_MODEL_CALLS, "org_procurement_demo")
        assert first == second
        assert {item["model_tier"] for item in first["breakdown"]} == {"light", "standard", "heavy"}
        assert first["total_cost_usd"] > 0
        assert first["total_saved_usd"] > 0
        assert first["data_source"] == "demo_estimate"
        assert first["execution_mode"] == "simulated"
        assert first["connection_status"] == "not_connected"
        assert compute_cost_estimation(DEMO_MODEL_CALLS, "other_org")["breakdown"] == []

    def test_cost_api_uses_real_postgresql_step_facts(self):
        from enterprise.dashboard import routes as cost_routes

        app = FastAPI()
        app.include_router(cost_routes.router)
        user = UserContext(
            user_id="eu_proc_admin",
            org_id="org_procurement_demo",
            department_roles=[
                DepartmentRole(
                    department_id="dept_it_procurement",
                    department_name="IT Procurement",
                    role="org_admin",
                ),
            ],
            business_line_ids=[],
        )
        from enterprise.auth.dependencies import require_any_operator

        app.dependency_overrides[require_any_operator] = lambda: user
        result = MagicMock()
        result.all.return_value = [
            (SimpleNamespace(input_token_count=100, output_token_count=20, cached_token_count=10, step_cost="0.01"), {"model_tier": "light"})
        ]
        session = AsyncMock()
        session.execute.return_value = result
        context = AsyncMock()
        context.__aenter__.return_value = session
        original_app = cost_routes.forge_app
        cost_routes.forge_app = SimpleNamespace(
            DATABASE=SimpleNamespace(Session=MagicMock(return_value=context))
        )
        try:
            response = TestClient(app).get("/enterprise/dashboard/cost")
        finally:
            cost_routes.forge_app = original_app
        assert response.status_code == 200
        body = response.json()
        assert body["data_source"] == "postgresql_steps"
        assert body["execution_mode"] == "real"
        assert body["connection_status"] == "connected"
        assert body["total_cached_tokens"] == 10
        assert body["total_cost_usd"] == 0.01


if __name__ == "__main__":
    unittest.main()
