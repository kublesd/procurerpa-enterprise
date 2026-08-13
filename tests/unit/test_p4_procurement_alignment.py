"""P4 acceptance checks for procurement Skills and workflow templates."""

import unittest
from unittest.mock import AsyncMock

from enterprise.skills.base import SKILL_REGISTRY, list_skills
from enterprise.skills.executor import execute_pipeline
from enterprise.workflows.templates import (
    MATERIAL_BENCHMARK_COLLECTION,
    PURCHASE_ORDER_DUE,
    TEMPLATE_REGISTRY,
    build_skill_pipeline,
)
from enterprise.workflows.schemas import ParamType


class TestP4ProcurementAlignment(unittest.TestCase):
    def test_exactly_seven_procurement_skills_are_registered(self):
        assert len(SKILL_REGISTRY) == 7
        assert {item["name"] for item in list_skills()} == {
            "login",
            "session_keep_alive",
            "form_fill",
            "search_and_select",
            "pagination",
            "table_extract",
            "file_download",
        }
        assert all(item["execution_mode"] == "simulated" for item in list_skills())

    def test_six_templates_have_procurement_scenario_categories(self):
        assert len(TEMPLATE_REGISTRY) == 6
        assert {template.industry.value for template in TEMPLATE_REGISTRY.values()} == {
            "direct_materials",
            "mro",
            "services",
        }
        assert all(template.skill_steps for template in TEMPLATE_REGISTRY.values())

    def test_every_template_validates_and_builds_pipeline_steps(self):
        for template in TEMPLATE_REGISTRY.values():
            parameters = {}
            for definition in template.parameters:
                if definition.default is not None:
                    parameters[definition.name] = definition.default
                elif definition.param_type == ParamType.URL:
                    parameters[definition.name] = "https://procurement.example.com"
                elif definition.param_type == ParamType.PASSWORD:
                    parameters[definition.name] = "demo-only"
                elif definition.param_type == ParamType.DATE:
                    parameters[definition.name] = "2026-01-01"
                elif definition.param_type == ParamType.INTEGER:
                    parameters[definition.name] = "7"
                else:
                    parameters[definition.name] = f"{definition.name}-demo"

            steps = build_skill_pipeline(template, parameters)
            assert steps[0].skill_name == "login"
            assert len(steps) == len(template.skill_steps)

    def test_build_pipeline_resolves_literals_and_placeholders(self):
        steps = build_skill_pipeline(
            MATERIAL_BENCHMARK_COLLECTION,
            {
                "pricing_portal_url": "https://pricing.example.com",
                "username": "buyer-demo",
                "password": "demo-only",
                "material_codes": "MAT-001,MAT-002",
                "start_date": "2026-01-01",
                "end_date": "2026-03-01",
            },
        )

        assert [step.skill_name for step in steps] == ["login", "form_fill", "table_extract"]
        assert steps[1].params["field_mapping"] == {
            "物料编码": "MAT-001,MAT-002",
            "开始日期": "2026-01-01",
            "结束日期": "2026-03-01",
        }
        assert steps[2].params["output_format"] == "csv"

    def test_invalid_template_parameters_fail(self):
        with self.assertRaises(ValueError):
            build_skill_pipeline(PURCHASE_ORDER_DUE, {"purchase_portal_url": "not-a-url"})


class TestP4FakePipeline(unittest.IsolatedAsyncioTestCase):
    async def test_procurement_template_executes_as_simulated_pipeline(self):
        steps = build_skill_pipeline(
            PURCHASE_ORDER_DUE,
            {
                "purchase_portal_url": "https://procurement.example.com",
                "username": "buyer-demo",
                "password": "demo-only",
                "days_ahead": "7",
            },
        )
        page = AsyncMock()
        page.query_selector = AsyncMock(return_value=AsyncMock())
        page.evaluate = AsyncMock(
            return_value={"headers": ["订单号", "交期", "状态"], "rows": [["PO-001", "2026-03-10", "待交付"]]}
        )
        llm_handler = AsyncMock()

        result = await execute_pipeline(
            steps,
            context={"page": page, "llm_handler": llm_handler},
        )

        assert result.success is True
        assert result.steps_completed == 3
        assert result.execution_mode == "simulated"
        assert result.step_results[1]["data"]["filled_fields"] == ["提前天数", "采购部门"]


if __name__ == "__main__":
    unittest.main()
