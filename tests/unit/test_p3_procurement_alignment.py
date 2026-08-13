"""Minimal P3 acceptance checks for the procurement agent chain."""

import json
import unittest

from enterprise.agent.executor import ExecutorAgent
from enterprise.agent.planner import PlannerAgent


class TestP3ProcurementAlignment(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_plan_has_procurement_steps_and_simulation_label(self):
        plan = await PlannerAgent().create_plan("Source 500 office chairs")

        self.assertGreaterEqual(len(plan.subtasks), 3)
        goals = " ".join(step.goal.lower() for step in plan.subtasks)
        for term in ("supplier", "rfq", "quote", "approval", "order"):
            self.assertIn(term, goals)

        result = await ExecutorAgent().execute_subtask(plan.subtasks[0])
        self.assertTrue(result.success)
        self.assertTrue(result.simulated)
        self.assertTrue(result.result_data["simulated"])

    async def test_planner_prompt_is_procurement_specific_and_sanitized(self):
        prompts = []

        async def llm(prompt):
            prompts.append(prompt)
            return json.dumps({
                "steps": [
                    {"goal": "Discover suppliers", "completion_condition": "Results visible"},
                    {"goal": "Collect RFQ quotes", "completion_condition": "Quotes available"},
                    {"goal": "Route comparison for approval", "completion_condition": "Approval recorded"},
                ]
            })

        planner = PlannerAgent(llm_callable=llm)
        plan = await planner.create_plan(
            "Source network equipment",
            context={
                "page_title": "Supplier quote page",
                "password": "demo-password",
                "token": "demo-token",
                "quote": "CNY 1000",
            },
        )

        self.assertEqual(len(plan.subtasks), 3)
        self.assertIn("procurement RPA", prompts[0])
        self.assertNotIn("demo-password", prompts[0])
        self.assertNotIn("demo-token", prompts[0])
        self.assertNotIn("CNY 1000", prompts[0])
        self.assertIn("********", prompts[0])

    async def test_fake_handler_returns_page_evidence_and_is_not_simulated(self):
        async def handler(_goal, _context):
            return {
                "success": True,
                "data": {"source": "synthetic-supplier-page"},
                "screenshot_key": "demo/p3/quote-page.png",
                "page_url": "https://supplier.example/quotes",
            }

        result = await ExecutorAgent(action_handler=handler).execute_subtask(
            (await PlannerAgent().create_plan("Source laptops")).subtasks[1]
        )

        self.assertTrue(result.success)
        self.assertFalse(result.simulated)
        self.assertEqual(result.screenshot_key, "demo/p3/quote-page.png")
        self.assertEqual(result.page_url, "https://supplier.example/quotes")


if __name__ == "__main__":
    unittest.main()
