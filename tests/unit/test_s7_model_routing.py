"""S7 real Skyvern model routing checks."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enterprise.agent import skyvern_handler as handler_module
from enterprise.audit.models import AuditLogModel
from enterprise.llm.action_cache import build_cache_key
from enterprise.llm.model_router import (
    ModelRoutingUnavailable,
    ModelTier,
    ProcurementPageKind,
    resolve_procurement_page,
)
from enterprise.procurement.models import ProcurementHumanReviewModel
from skyvern.config import settings
from skyvern.forge.agent import ForgeAgent
from tests.unit.test_s3_skyvern_executor import Database, make_handler

MODEL_MAPPING = {
    "light-model": {"llm_key": "LIGHT_KEY", "label": "Light"},
    "standard-model": {"llm_key": "STANDARD_KEY", "label": "Standard"},
    "heavy-model": {"llm_key": "HEAVY_KEY", "label": "Heavy"},
}


def configure_tiers(monkeypatch):
    monkeypatch.setattr(settings, "PROCUREMENT_LIGHT_LLM_KEY", "LIGHT_KEY")
    monkeypatch.setattr(settings, "PROCUREMENT_STANDARD_LLM_KEY", "STANDARD_KEY")
    monkeypatch.setattr(settings, "PROCUREMENT_HEAVY_LLM_KEY", "HEAVY_KEY")


def test_three_page_kinds_resolve_to_configured_native_models(monkeypatch):
    configure_tiers(monkeypatch)
    expected = {
        ProcurementPageKind.SUPPLIER_CATALOG: ModelTier.LIGHT,
        ProcurementPageKind.DYNAMIC_QUOTE_PORTAL: ModelTier.STANDARD,
        ProcurementPageKind.ERP_CONTRACT: ModelTier.HEAVY,
    }

    for page_kind, tier in expected.items():
        decision = resolve_procurement_page(
            page_kind,
            available_keys={"LIGHT_KEY", "STANDARD_KEY", "HEAVY_KEY"},
            model_mapping=MODEL_MAPPING,
        )
        assert decision.model_tier == tier
        assert decision.resolved_model_key == f"{tier.value.upper()}_KEY"
        assert decision.execution_mode == "real"
        assert decision.connection_status == "connected"


def test_heavy_route_falls_back_only_to_configured_standard_then_light(monkeypatch):
    configure_tiers(monkeypatch)
    decision = resolve_procurement_page(
        ProcurementPageKind.ERP_CONTRACT,
        available_keys={"STANDARD_KEY", "LIGHT_KEY"},
        model_mapping=MODEL_MAPPING,
    )

    assert decision.resolved_model_key == "STANDARD_KEY"
    assert decision.reason_code == "heavy_fallback_to_standard"
    with pytest.raises(ModelRoutingUnavailable):
        resolve_procurement_page(
            ProcurementPageKind.ERP_CONTRACT,
            available_keys=set(),
            model_mapping=MODEL_MAPPING,
        )


def test_action_cache_key_isolated_by_resolved_model():
    args = ("org_a", "dom_hash", "goal_hash")
    assert build_cache_key(*args, "LIGHT_KEY", "v1") != build_cache_key(*args, "HEAVY_KEY", "v1")


@pytest.mark.asyncio
async def test_real_step_call_records_only_safe_route_metadata():
    agent = ForgeAgent()
    audit = AsyncMock()
    agent._audit_procurement_model_call = audit
    task = SimpleNamespace(
        task_id="task_a",
        organization_id="org_a",
        model={"llm_key": "STANDARD_KEY", "model_tier": "standard", "reason_code": "tier_selected"},
    )
    step = SimpleNamespace(step_id="step_a", order=2)
    page = SimpleNamespace(screenshots=[])
    llm = AsyncMock(return_value={"actions": [{"action_type": "WAIT"}]})

    result = await agent._resolve_action_response(
        task=task,
        step=step,
        scraped_page=page,
        llm_api_handler=llm,
        prompt="synthetic prompt that must not be audited",
        prompt_name="extract-actions",
    )

    assert result["actions"][0]["action_type"] == "WAIT"
    audit.assert_awaited_once()
    assert audit.await_args.args[:2] == (task, step)
    assert "prompt" not in audit.await_args.kwargs


@pytest.mark.asyncio
async def test_native_handler_passes_model_to_task_and_writes_safe_route_audit():
    database, calls = Database(), []
    result = await make_handler(database, calls)("ignored", {})

    request = calls[0]["task"]
    assert request.llm_key == request.model["llm_key"]
    assert result["model_alias"].startswith("procurement-")
    route_audit = next(
        row for row in database.rows if isinstance(row, AuditLogModel) and row.action_type == "model_route"
    )
    details = json.loads(route_audit.input_value)
    assert details == {
        "model_tier": result["model_tier"],
        "resolved_model_key": request.model["llm_key"],
        "reason_code": result["routing_reason_code"],
        "step_id": None,
    }
    assert "API_KEY" not in result


@pytest.mark.asyncio
async def test_no_configured_model_creates_review_without_running_llm(monkeypatch):
    database, calls = Database(), []

    def unavailable(_page_kind):
        raise ModelRoutingUnavailable("procurement_model_unavailable")

    monkeypatch.setattr(handler_module, "resolve_procurement_page", unavailable)
    result = await make_handler(database, calls)("ignored", {})

    assert result["error"] == "procurement_model_unavailable"
    assert calls[0]["defer_execution"] is True
    assert any(
        isinstance(row, ProcurementHumanReviewModel)
        and row.reason_code == "procurement_model_unavailable"
        for row in database.rows
    )


@pytest.mark.asyncio
async def test_real_step_model_call_audit_contains_only_safe_routing_fields():
    session = AsyncMock()
    session.scalar.return_value = SimpleNamespace(department_id="dept_a")
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    session_context.__aexit__ = AsyncMock(return_value=None)
    database = SimpleNamespace(Session=MagicMock(return_value=session_context))
    writer = AsyncMock()
    task = SimpleNamespace(
        task_id="tsk_a",
        organization_id="org_a",
        model={"llm_key": "STANDARD_KEY", "model_tier": "standard", "reason_code": "tier_selected"},
    )
    step = SimpleNamespace(step_id="step_a", order=2)

    with patch("skyvern.forge.agent.app", SimpleNamespace(DATABASE=database)), patch(
        "skyvern.forge.agent.write_audit_log", writer
    ):
        await ForgeAgent._audit_procurement_model_call(task, step, 123, "success")

    details = writer.await_args.kwargs["input_value"]
    assert details == {
        "model_tier": "standard",
        "resolved_model_key": "STANDARD_KEY",
        "reason_code": "tier_selected",
        "step_id": "step_a",
    }
    assert writer.await_args.kwargs["duration_ms"] == 123
