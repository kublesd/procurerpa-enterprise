"""Database-backed single-level procurement approval routes."""

import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from enterprise.audit.logger import record_audit_event
from enterprise.audit.models import ActionType
from enterprise.auth.dependencies import require_any_operator, require_approver
from enterprise.auth.models import TaskExtensionModel
from enterprise.auth.schemas import UserContext
from skyvern.forge import app as forge_app
from skyvern.forge.sdk.executor.factory import AsyncExecutorFactory
from skyvern.forge.sdk.schemas.tasks import TaskStatus

from .models import ApprovalRequestModel, ApprovalStatus

router = APIRouter(prefix="/enterprise/approvals", tags=["approvals"])


class ApprovalResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    approval_id: str
    task_id: str
    organization_id: str
    department_id: str
    business_line_id: str | None
    requester_user_id: str
    risk_level: str
    risk_reason: str
    operation_description: str | None
    screenshot_path: str | None
    approver_department_id: str
    status: str
    requested_at: datetime.datetime
    timeout_seconds: int


class DecisionRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class DecisionResponse(BaseModel):
    approval_id: str
    status: str
    decided_at: datetime.datetime
    message: str


class ContinueResponse(BaseModel):
    approval_id: str
    task_id: str
    task_status: str


def _user_can_approve(
    user: UserContext,
    approval: ApprovalRequestModel,
    category_id: str | None = None,
) -> bool:
    category_id = category_id or getattr(approval, "category_id", None)
    if approval.organization_id != user.org_id or approval.requester_user_id == user.user_id:
        return False
    if user.is_org_admin or user.has_cross_org_approve:
        return True
    if category_id is not None and not user.has_procurement_category(category_id):
        return False
    return user.get_role_in_department(approval.approver_department_id) == "approver"


async def _locked_approval(session, approval_id: str) -> ApprovalRequestModel:
    approval = await session.scalar(
        select(ApprovalRequestModel)
        .where(ApprovalRequestModel.approval_id == approval_id)
        .with_for_update()
    )
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    return approval


@router.get("/pending", response_model=list[ApprovalResponseSchema])
async def list_pending_approvals(user: UserContext = Depends(require_approver)):
    statement = select(ApprovalRequestModel).where(
        ApprovalRequestModel.organization_id == user.org_id,
        ApprovalRequestModel.status == ApprovalStatus.PENDING.value,
        ApprovalRequestModel.requester_user_id != user.user_id,
    )
    if not (user.is_org_admin or user.has_cross_org_approve):
        departments = [
            role.department_id
            for role in user.department_roles
            if role.role == "approver"
        ]
        statement = statement.where(ApprovalRequestModel.approver_department_id.in_(departments))
        if user.procurement_category_ids:
            statement = statement.where(
                select(TaskExtensionModel.task_id)
                .where(
                    TaskExtensionModel.task_id == ApprovalRequestModel.task_id,
                    TaskExtensionModel.organization_id == user.org_id,
                    TaskExtensionModel.category_id.in_(user.procurement_category_ids),
                )
                .exists()
            )
        else:
            statement = statement.where(False)
    async with forge_app.DATABASE.Session() as session:
        return (await session.scalars(statement.order_by(ApprovalRequestModel.requested_at))).all()


async def _decide(
    approval_id: str,
    decision: ApprovalStatus,
    note: str,
    user: UserContext,
) -> DecisionResponse:
    async with forge_app.DATABASE.Session() as session:
        approval = await _locked_approval(session, approval_id)
        if approval.organization_id != user.org_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-organization approval is forbidden")
        if approval.requester_user_id == user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Requesters cannot approve their own task")
        # ponytail: category scope is read from TaskExtension until approval routing gets its own persisted category column.
        category_id = await session.scalar(
            select(TaskExtensionModel.category_id).where(
                TaskExtensionModel.task_id == approval.task_id,
                TaskExtensionModel.organization_id == approval.organization_id,
            )
        )
        if not _user_can_approve(user, approval, category_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Approval is outside the user's department or procurement category",
            )
        if approval.status != ApprovalStatus.PENDING.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Approval is already {approval.status}")

        task = await forge_app.DATABASE.get_task(approval.task_id, organization_id=approval.organization_id)
        if task is None or task.status != TaskStatus.created:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Procurement task is no longer awaiting approval")

        now = datetime.datetime.utcnow()
        approval.status = decision.value
        approval.approver_user_id = user.user_id
        approval.decided_at = now
        approval.decision_note = note
        audit_context = {
            "task_id": approval.task_id,
            "org_id": approval.organization_id,
            "department_id": approval.department_id,
            "business_line_id": approval.business_line_id,
        }
        if decision is ApprovalStatus.REJECTED:
            await forge_app.DATABASE.update_task(
                approval.task_id,
                status=TaskStatus.canceled,
                organization_id=approval.organization_id,
            )
        await session.commit()
    await record_audit_event(
        **audit_context,
        business_object_type="approval",
        business_object_id=approval_id,
        action_index=4,
        action_type=(
            ActionType.APPROVAL_APPROVED.value
            if decision is ApprovalStatus.APPROVED
            else ActionType.APPROVAL_REJECTED.value
        ),
        executor=user.user_id,
        input_value={"decision_note": note},
        execution_result=decision.value,
        has_approval=True,
        approval_id=approval_id,
        approver_user_id=user.user_id,
    )
    return DecisionResponse(
        approval_id=approval_id,
        status=decision.value,
        decided_at=now,
        message="Approval granted" if decision is ApprovalStatus.APPROVED else "Approval rejected",
    )


@router.post("/{approval_id}/approve", response_model=DecisionResponse)
async def approve_request(
    approval_id: str,
    body: DecisionRequest = DecisionRequest(),
    user: UserContext = Depends(require_approver),
):
    return await _decide(approval_id, ApprovalStatus.APPROVED, body.note, user)


@router.post("/{approval_id}/reject", response_model=DecisionResponse)
async def reject_request(
    approval_id: str,
    body: DecisionRequest = DecisionRequest(),
    user: UserContext = Depends(require_approver),
):
    return await _decide(approval_id, ApprovalStatus.REJECTED, body.note, user)


@router.post("/{approval_id}/continue", response_model=ContinueResponse)
async def continue_request(
    approval_id: str,
    background_tasks: BackgroundTasks,
    user: UserContext = Depends(require_any_operator),
):
    async with forge_app.DATABASE.Session() as session:
        approval = await _locked_approval(session, approval_id)
        if approval.organization_id != user.org_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-organization continuation is forbidden")
        if approval.requester_user_id != user.user_id and not user.is_org_admin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the requester can continue this task")
        if approval.status != ApprovalStatus.APPROVED.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved tasks can continue")

        approval_data = {
            "approval_id": approval.approval_id,
            "task_id": approval.task_id,
            "organization_id": approval.organization_id,
            "department_id": approval.department_id,
            "business_line_id": approval.business_line_id,
            "approver_user_id": approval.approver_user_id,
        }
        task = await forge_app.DATABASE.get_task(
            approval_data["task_id"], organization_id=approval_data["organization_id"],
        )
        if task is None or task.status != TaskStatus.created:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Procurement task has already continued")
        # Claim the task while the approval row is locked so concurrent retries
        # cannot schedule the same native Task twice.
        await forge_app.DATABASE.update_task(
            approval_data["task_id"],
            status=TaskStatus.running,
            organization_id=approval_data["organization_id"],
        )
        browser_session_id = task.browser_session_id

    try:
        await AsyncExecutorFactory.get_executor().execute_task(
            request=None,
            background_tasks=background_tasks,
            task_id=approval_data["task_id"],
            organization_id=approval_data["organization_id"],
            max_steps_override=None,
            browser_session_id=browser_session_id,
            api_key=None,
        )
    except Exception as exc:
        try:
            await forge_app.DATABASE.update_task(
                approval_data["task_id"],
                status=TaskStatus.failed,
                organization_id=approval_data["organization_id"],
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Approved procurement task could not be started",
        ) from exc
    await record_audit_event(
        task_id=approval_data["task_id"],
        org_id=approval_data["organization_id"],
        department_id=approval_data["department_id"],
        business_line_id=approval_data["business_line_id"],
        business_object_type="approval",
        business_object_id=approval_data["approval_id"],
        action_index=5,
        action_type=ActionType.TASK_CONTINUED.value,
        executor=user.user_id,
        execution_result="running",
        has_approval=True,
        approval_id=approval_data["approval_id"],
        approver_user_id=approval_data["approver_user_id"],
    )
    return ContinueResponse(
        approval_id=approval_data["approval_id"],
        task_id=approval_data["task_id"],
        task_status=TaskStatus.running.value,
    )
