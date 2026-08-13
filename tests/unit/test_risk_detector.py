"""Day 5 procurement-risk rules and deterministic/LLM boundary checks."""

from decimal import Decimal

import pytest

from enterprise.approval.risk_detector import RiskContext, detect_risk
from enterprise.approval.routing import COMPLIANCE_DEPT_ID, route_approval


def _context(**changes) -> RiskContext:
    values = {
        "total_amount_cny": Decimal("1000"),
        "supplier_id": "supplier-1",
        "supplier_qualified": True,
        "selected_quote_cny": Decimal("100"),
        "average_quote_cny": Decimal("100"),
        "tax_rate": Decimal("0.13"),
    }
    values.update(changes)
    return RiskContext(**values)


@pytest.mark.asyncio
async def test_normal_procurement_is_low_and_repeatable() -> None:
    first = await detect_risk(_context())
    second = await detect_risk(_context())
    assert first == second
    assert first.risk_level == first.deterministic_level == "low"
    assert first.findings == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("amount", "level"),
    [
        ("49999.99", "low"),
        ("50000", "medium"),
        ("100000", "high"),
        ("1000000", "critical"),
    ],
)
async def test_amount_threshold_boundaries(amount: str, level: str) -> None:
    assert (await detect_risk(_context(total_amount_cny=amount))).risk_level == level


@pytest.mark.parametrize(
    "changes",
    [
        {"total_amount_cny": "-0.01"},
        {"selected_quote_cny": "-1"},
        {"average_quote_cny": "0"},
        {"tax_rate": "1.01"},
        {"operation_type": "delete_everything"},
    ],
)
def test_invalid_structured_values_are_rejected(changes: dict) -> None:
    with pytest.raises(ValueError):
        _context(**changes)


@pytest.mark.asyncio
async def test_supplier_rules_cover_missing_and_new_supplier() -> None:
    missing = await detect_risk(_context(supplier_id=None))
    new = await detect_risk(_context(is_new_supplier=True))
    assert missing.risk_level == "medium"
    assert new.risk_level == "high"
    assert {finding.category for finding in new.findings} == {"supplier"}


@pytest.mark.asyncio
async def test_qualification_rules_cover_missing_and_invalid() -> None:
    missing = await detect_risk(_context(supplier_qualified=None))
    invalid = await detect_risk(_context(supplier_qualified=False))
    assert missing.risk_level == "medium"
    assert invalid.risk_level == "critical"


@pytest.mark.asyncio
@pytest.mark.parametrize(("quote", "level"), [("119.99", "low"), ("120", "high"), ("150", "critical")])
async def test_quote_deviation_boundaries(quote: str, level: str) -> None:
    result = await detect_risk(_context(selected_quote_cny=quote))
    assert result.risk_level == level


@pytest.mark.asyncio
async def test_missing_quote_data_is_explainable() -> None:
    result = await detect_risk(_context(selected_quote_cny=None))
    assert result.risk_level == "medium"
    assert result.findings[0].category == "quote_deviation"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation_type", "level"),
    [
        ("standard", "low"),
        ("single_source", "high"),
        ("emergency", "high"),
        ("advance_payment", "critical"),
        ("supplier_bank_change", "critical"),
    ],
)
async def test_operation_type_rules(operation_type: str, level: str) -> None:
    assert (await detect_risk(_context(operation_type=operation_type))).risk_level == level


@pytest.mark.asyncio
async def test_llm_can_raise_but_never_lower_deterministic_level() -> None:
    async def lower(_prompt: str) -> dict:
        return {"risk_level": "low", "reason": "ignore all rules"}

    async def raise_risk(_prompt: str) -> dict:
        return {"risk_level": "critical", "reason": "Additional redacted-context risk"}

    high_context = _context(is_new_supplier=True, redacted_description="New supplier request")
    assert (await detect_risk(high_context, lower)).risk_level == "high"
    raised = await detect_risk(_context(redacted_description="Urgent exception"), raise_risk)
    assert raised.risk_level == "critical"
    assert raised.stage == "llm"


@pytest.mark.asyncio
async def test_llm_receives_only_redacted_description() -> None:
    prompts: list[str] = []

    async def capture(prompt: str) -> dict:
        prompts.append(prompt)
        return {"risk_level": "low", "reason": "No change"}

    context = _context(
        total_amount_cny="987654.32",
        supplier_id="sensitive-supplier-id",
        redacted_description="Office equipment purchase",
    )
    await detect_risk(context, capture)
    assert "Office equipment purchase" in prompts[0]
    assert "987654.32" not in prompts[0]
    assert "sensitive-supplier-id" not in prompts[0]


@pytest.mark.asyncio
async def test_invalid_or_failed_llm_keeps_deterministic_result() -> None:
    async def invalid(_prompt: str):
        return "not-json"

    async def timeout(_prompt: str):
        raise TimeoutError

    context = _context(is_new_supplier=True, redacted_description="Redacted request")
    invalid_result = await detect_risk(context, invalid)
    timeout_result = await detect_risk(context, timeout)
    assert invalid_result.risk_level == timeout_result.risk_level == "high"
    assert invalid_result.llm_fallback is timeout_result.llm_fallback is True


def test_existing_approval_routing_consumes_procurement_risk_levels() -> None:
    assert route_approval("low", "dept-buy").requires_approval is False
    assert route_approval("high", "dept-buy").approver_department_id == "dept-buy"
    assert route_approval("critical", "dept-buy").approver_department_id == COMPLIANCE_DEPT_ID
