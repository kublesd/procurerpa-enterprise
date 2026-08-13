"""Minimal P1 acceptance checks for procurement risk and approval scope."""

from decimal import Decimal

import pytest

from enterprise.approval.models import ApprovalRequestModel
from enterprise.approval.risk_detector import RiskContext, detect_risk
from enterprise.approval.routes import _user_can_approve
from enterprise.approval.routing import route_approval
from enterprise.auth.permission import PermissionLevel, resolve_permission
from enterprise.auth.schemas import DepartmentRole, UserContext


def _context(**changes) -> RiskContext:
    values = {
        "total_amount_cny": Decimal("1000"),
        "supplier_id": "supplier-demo",
        "supplier_qualified": True,
        "selected_quote_cny": Decimal("100"),
        "average_quote_cny": Decimal("100"),
    }
    values.update(changes)
    return RiskContext(**values)


def _approver() -> UserContext:
    return UserContext(
        user_id="approver-demo",
        org_id="org-demo",
        department_roles=[DepartmentRole(department_id="dept-buy", department_name="采购部", role="approver")],
        procurement_category_ids=["pc-it"],
    )


@pytest.mark.asyncio
async def test_procurement_keywords_and_text_amounts_raise_risk() -> None:
    keyword_result = await detect_risk(_context(redacted_description="供应商资质过期，异常报价，银行账户变更"))
    amount_result = await detect_risk(_context(redacted_description="大额采购，金额 12 万元"))

    assert keyword_result.risk_level == "critical"
    assert {"supplier_qualification", "quote_anomaly", "supplier_bank_change"} <= {
        finding.category for finding in keyword_result.findings
    }
    assert amount_result.risk_level == "high"


@pytest.mark.asyncio
async def test_stage2_uses_procurement_prompt_and_reason() -> None:
    prompts = []

    async def llm(prompt: str) -> dict:
        prompts.append(prompt)
        return {"risk_level": "critical", "reason": "采购合规要求复核供应商账户"}

    result = await detect_risk(_context(redacted_description="单一来源采购"), llm)

    assert result.stage == "llm"
    assert result.reason == "采购合规要求复核供应商账户"
    assert "procurement compliance" in prompts[0].lower()


@pytest.mark.asyncio
async def test_stage2_failure_is_conservative() -> None:
    async def fail(_prompt: str) -> dict:
        raise TimeoutError

    result = await detect_risk(_context(redacted_description="单一来源采购"), fail)

    assert result.risk_level == "high"
    assert result.llm_fallback is True


def test_permission_and_approval_are_category_scoped() -> None:
    user = _approver()
    approval = ApprovalRequestModel(
        approval_id="apr-demo",
        task_id="task-demo",
        organization_id="org-demo",
        department_id="dept-buy",
        requester_user_id="buyer-demo",
        approver_department_id="dept-buy",
        risk_level="high",
        risk_reason="采购风险",
    )

    assert resolve_permission(user, "org-demo", "dept-buy", resource_category_id="pc-it") == PermissionLevel.APPROVE
    assert resolve_permission(user, "org-demo", "dept-buy", resource_category_id="pc-services") == PermissionLevel.NONE
    assert resolve_permission(user, "other-org", "dept-buy", resource_category_id="pc-it") == PermissionLevel.NONE
    assert _user_can_approve(user, approval, "pc-it") is True
    assert _user_can_approve(user, approval, "pc-services") is False


def test_high_risk_route_keeps_procurement_category() -> None:
    route = route_approval("high", "dept-buy", procurement_category_id="pc-it")

    assert route.requires_approval is True
    assert route.approver_department_id == "dept-buy"
    assert route.approver_category_id == "pc-it"
