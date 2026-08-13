"""S1 durable procurement human-review checks."""

# ruff: noqa: E402

import datetime
import sys
import types
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, status

# The checkout omits Skyvern's unrelated workflow block module; keep this unit
# test scoped to the procurement route without changing that existing surface.
_task_service_stub = types.ModuleType("skyvern.services.task_v1_service")
_task_service_stub.run_task = None
sys.modules.setdefault("skyvern.services.task_v1_service", _task_service_stub)

from enterprise.auth.schemas import DepartmentRole, UserContext
from enterprise.llm.human_intervention import ResolutionAction
from enterprise.procurement import routes
from enterprise.procurement.models import (
    HumanReviewStatus,
    ProcurementHumanReviewModel,
    SupplierQuoteModel,
)
from skyvern.forge.sdk.schemas.tasks import TaskStatus


def _user(
    user_id: str = "operator_a",
    org_id: str = "org_a",
    department_id: str = "dept_a",
    category_id: str = "pc_a",
    role: str = "operator",
) -> UserContext:
    return UserContext(
        user_id=user_id,
        org_id=org_id,
        department_roles=[DepartmentRole(department_id=department_id, department_name=department_id, role=role)],
        procurement_category_ids=[category_id],
    )


def _payload() -> routes.QuoteTaskRequest:
    return routes.QuoteTaskRequest(
        organization_id="org_a",
        department_id="dept_a",
        category_id="pc_a",
        url="https://supplier.example/quote",
    )


class _Database:
    def __init__(self):
        self.review = None
        self.quote = None
        self.context = SimpleNamespace(
            task_id="task_a",
            department_id="dept_a",
            category_id="pc_a",
            business_line_id=None,
        )
        self.artifact = "artifact_a"

    def Session(self):
        return _Session(self)


class _Session:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def scalar(self, statement):
        sql = str(statement)
        if "procurement_human_reviews" in sql:
            return self.database.review
        if "task_extensions" in sql:
            return self.database.context
        if "artifacts" in sql:
            return self.database.artifact
        return None

    def add(self, value):
        if isinstance(value, ProcurementHumanReviewModel):
            self.database.review = value
        elif isinstance(value, SupplierQuoteModel):
            self.database.quote = value

    async def commit(self):
        if self.database.review is not None and self.database.review.created_at is None:
            self.database.review.created_at = datetime.datetime.utcnow()

    async def refresh(self, _value):
        return None

    async def rollback(self):
        return None


def _task(**changes):
    values = {
        "task_id": "task_a",
        "status": TaskStatus.completed,
        "extracted_information": {
            "supplier_id": "supplier-a",
            "material_name": "SSD",
            "quantity": "10",
            "unit": "unit",
            "currency": "CNY",
            "unit_price_cny": "10.00",
            "freight_cny": "1.00",
            "moq": "1",
            "delivery_days": 5,
            "confidence": "0.20",
        },
    }
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_quote_failure_creates_one_pending_review_and_reuses_it(monkeypatch):
    database = _Database()
    audit = AsyncMock()
    monkeypatch.setattr(routes, "forge_app", SimpleNamespace(DATABASE=database))
    monkeypatch.setattr(routes, "record_audit_event", audit)

    with pytest.raises(HTTPException) as first:
        await routes._persist_extracted_quote(_task(), _payload(), _user())
    with pytest.raises(HTTPException) as second:
        await routes._persist_extracted_quote(_task(), _payload(), _user())

    assert first.value.detail["review_id"] == second.value.detail["review_id"]
    assert database.review.status == HumanReviewStatus.PENDING.value
    assert database.review.artifact_id == "artifact_a"
    assert audit.await_count == 1


@pytest.mark.asyncio
async def test_manual_complete_validates_artifact_and_persists_quote(monkeypatch):
    database = _Database()
    database.review = ProcurementHumanReviewModel(
        review_id="phr_a",
        task_id="task_a",
        organization_id="org_a",
        department_id="dept_a",
        category_id="pc_a",
        status=HumanReviewStatus.PENDING.value,
        reason_code="quote_schema_invalid",
        safe_error_summary="Extracted quote fields failed server validation",
        artifact_id="artifact_a",
        action_index=0,
        action_type="quote_extraction",
        created_by="operator_a",
        created_at=datetime.datetime.utcnow(),
    )
    audit = AsyncMock()
    monkeypatch.setattr(routes, "forge_app", SimpleNamespace(DATABASE=database))
    monkeypatch.setattr(routes, "record_audit_event", audit)

    result = await routes.resolve_human_review(
        "phr_a",
        routes.HumanReviewResolutionRequest(
            action=ResolutionAction.MANUAL_COMPLETE,
            manual_result=routes.ManualQuoteResult(
                supplier_id="supplier-a",
                material_name="SSD",
                quantity="10",
                unit="unit",
                currency="CNY",
                unit_price_cny="10.005",
                freight_cny="1.005",
                moq="1",
                delivery_days=5,
            ),
        ),
        _user(),
    )

    assert result.status == HumanReviewStatus.RESOLVED.value
    assert result.quote_id is not None
    assert database.quote.unit_price_cny == Decimal("10.01")
    assert database.review.resolution_action == ResolutionAction.MANUAL_COMPLETE.value
    assert audit.await_args.kwargs["action_type"] == "human_review_resolved"


@pytest.mark.asyncio
async def test_skip_and_terminate_persist_distinct_resolution_states(monkeypatch):
    database = _Database()
    database.review = ProcurementHumanReviewModel(
        review_id="phr_skip",
        task_id="task_a",
        organization_id="org_a",
        department_id="dept_a",
        category_id="pc_a",
        status=HumanReviewStatus.PENDING.value,
        reason_code="quote_artifact_missing",
        safe_error_summary="No browser evidence artifact was recorded",
        action_index=0,
        action_type="quote_extraction",
        created_by="operator_a",
        created_at=datetime.datetime.utcnow(),
    )
    audit = AsyncMock()
    monkeypatch.setattr(routes, "forge_app", SimpleNamespace(DATABASE=database))
    monkeypatch.setattr(routes, "record_audit_event", audit)

    skipped = await routes.resolve_human_review(
        "phr_skip",
        routes.HumanReviewResolutionRequest(action=ResolutionAction.SKIP_STEP),
        _user(),
    )
    assert skipped.status == HumanReviewStatus.RESOLVED.value
    assert skipped.resolution_action == ResolutionAction.SKIP_STEP.value

    database.review = ProcurementHumanReviewModel(
        review_id="phr_terminate",
        task_id="task_a",
        organization_id="org_a",
        department_id="dept_a",
        category_id="pc_a",
        status=HumanReviewStatus.PENDING.value,
        reason_code="task_not_completed",
        safe_error_summary="Skyvern quote task did not complete",
        action_index=0,
        action_type="quote_extraction",
        created_by="operator_a",
        created_at=datetime.datetime.utcnow(),
    )
    terminated = await routes.resolve_human_review(
        "phr_terminate",
        routes.HumanReviewResolutionRequest(action=ResolutionAction.TERMINATE),
        _user(),
    )
    assert terminated.status == HumanReviewStatus.TERMINATED.value
    assert terminated.resolution_action == ResolutionAction.TERMINATE.value
    assert audit.await_args_list[-1].kwargs["action_type"] == "human_review_terminated"


@pytest.mark.asyncio
async def test_cross_scope_review_is_not_resolvable(monkeypatch):
    database = _Database()
    database.review = ProcurementHumanReviewModel(
        review_id="phr_a",
        task_id="task_a",
        organization_id="org_a",
        department_id="dept_a",
        category_id="pc_a",
        status=HumanReviewStatus.PENDING.value,
        reason_code="quote_schema_invalid",
        safe_error_summary="Extracted quote fields failed server validation",
        action_index=0,
        action_type="quote_extraction",
        created_by="operator_a",
        created_at=datetime.datetime.utcnow(),
    )
    monkeypatch.setattr(routes, "forge_app", SimpleNamespace(DATABASE=database))

    with pytest.raises(HTTPException) as denied:
        await routes.resolve_human_review("phr_a", routes.HumanReviewResolutionRequest(action=ResolutionAction.SKIP_STEP), _user(department_id="dept_b", category_id="pc_b"))

    assert denied.value.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
