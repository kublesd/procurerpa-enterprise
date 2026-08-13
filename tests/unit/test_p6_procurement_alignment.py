"""P6 acceptance check for the single procurement parity demo entry point."""

import json
import unittest

from scripts.demo_procurement_parity import run_demo


class TestP6ProcurementAlignment(unittest.IsolatedAsyncioTestCase):
    async def test_one_entry_exposes_procurement_results_and_boundaries(self):
        result = await run_demo()

        self.assertEqual(result["demo"]["task_id"], "task_p6_procurement_demo")
        self.assertEqual(
            set(result["demo"]["labels"]),
            {"demo", "simulated", "not_connected"},
        )

        risk = result["p1_risk_approval"]
        self.assertEqual(risk["risk_level"], "high")
        self.assertTrue(risk["approval_route"]["requires_approval"])
        self.assertEqual(risk["approval_route"]["approver_category_id"], "pc-it")
        self.assertEqual(risk["approver_permission"], "approve")

        resilience = result["p2_llm_resilience"]
        self.assertEqual(resilience["structured_json"]["attempts"], 2)
        self.assertEqual(resilience["needs_human"]["status"], "needs_human")
        self.assertEqual(resilience["needs_human"]["resolution"], "manual_complete")
        self.assertTrue(resilience["needs_human"]["transition_valid"])

        planner = result["p3_planner_executor"]
        self.assertEqual(planner["status"], "completed")
        self.assertEqual(planner["subtask_count"], 6)
        self.assertTrue(planner["all_steps_simulated"])

        pipeline = result["p4_skill_pipeline"]
        self.assertEqual(pipeline["template_id"], "tpl_purchase_order_due")
        self.assertTrue(pipeline["success"])
        self.assertEqual(pipeline["steps_completed"], 3)
        self.assertTrue(pipeline["fake_page"])
        self.assertEqual(pipeline["execution_mode"], "simulated")

        model_cache = result["p5_model_cache_cost"]
        self.assertEqual(
            {item["model_tier"] for item in model_cache["model_routing"].values()},
            {"light", "standard", "heavy"},
        )
        self.assertTrue(model_cache["cache"]["initial_miss"])
        self.assertTrue(model_cache["cache"]["same_page_hit"])
        self.assertTrue(model_cache["cache"]["changed_dom_miss"])
        self.assertGreater(model_cache["cost"]["total_saved_usd"], 0)
        self.assertEqual(model_cache["cost"]["data_source"], "demo_estimate")

        audit = result["demo_audit_summary"]
        self.assertEqual(audit["approval_status"], "pending_approval")
        self.assertEqual(audit["plan_status"], "completed")
        self.assertTrue(audit["cache_hit"])
        self.assertIn("human_resolution_applied", audit["event_types"])
        self.assertEqual(audit["persistence"], "not_connected")

        self.assertEqual(result["real_procurement_main_chain"]["status"], "preserved")
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("demo-password", serialized)
        self.assertNotIn("demo-token", serialized)


if __name__ == "__main__":
    unittest.main()
