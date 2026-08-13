"""Database-backed procurement audit queries and quote-file upload."""

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import false, func, select

from enterprise.auth.dependencies import CurrentUser, require_any_operator
from enterprise.auth.models import TaskExtensionModel
from enterprise.auth.schemas import UserContext
from skyvern.config import settings
from skyvern.forge import app as forge_app
from skyvern.forge.sdk.artifact.models import ArtifactType
from skyvern.forge.sdk.db.id import generate_artifact_id
from skyvern.forge.sdk.db.models import TaskModel

from .logger import record_audit_event
from .models import ActionType, AuditLogModel
from .storage import (
    generate_quote_object_key,
    get_bucket_name,
    get_minio_client,
    get_presigned_url,
    split_minio_uri,
    upload_file,
)

router = APIRouter(prefix="/enterprise/audit", tags=["audit"])


class AuditLogResponse(BaseModel):
    audit_log_id: str
    task_id: str
    organization_id: str
    department_id: str
    business_line_id: str | None
    business_object_type: str | None
    business_object_id: str | None
    action_index: int
    action_type: str
    target_element: str | None
    input_value: str | None
    page_url: str | None
    screenshot_before_url: str | None
    screenshot_after_url: str | None
    duration_ms: int | None
    executor: str
    execution_result: str
    error_message: str | None
    has_approval: bool
    approval_id: str | None
    approver_user_id: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


class QuoteFileResponse(BaseModel):
    artifact_id: str
    task_id: str
    object_uri: str
    presigned_url: str | None


def _can_view_audit(user: UserContext) -> bool:
    return user.is_org_admin or user.has_cross_org_read or bool(_department_ids_for_role(user, "viewer"))


def _department_ids_for_role(user: UserContext, role: str) -> list[str]:
    return [assignment.department_id for assignment in user.department_roles if assignment.role == role]


async def _screenshot_url(client, key: str | None, created_at: datetime) -> str | None:
    if client is None or not key:
        return None
    try:
        bucket, object_key = split_minio_uri(key) if key.startswith("minio://") else (get_bucket_name(created_at), key)
        return await get_presigned_url(client, bucket, object_key)
    except Exception:
        return None


@router.get("/logs", response_model=AuditLogListResponse)
async def query_audit_logs(
    user: CurrentUser,
    task_id: str | None = None,
    action_type: str | None = None,
    executor: str | None = None,
    business_object_type: str | None = None,
    business_object_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> AuditLogListResponse:
    if not _can_view_audit(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Audit viewer role required")

    conditions = [AuditLogModel.organization_id == user.org_id]
    if not (user.is_org_admin or user.has_cross_org_read):
        department_ids = _department_ids_for_role(user, "viewer")
        if not department_ids or not user.procurement_category_ids:
            conditions.append(false())
        else:
            conditions.append(
                select(TaskExtensionModel.task_id)
                .where(
                    TaskExtensionModel.task_id == AuditLogModel.task_id,
                    TaskExtensionModel.organization_id == user.org_id,
                    TaskExtensionModel.department_id.in_(department_ids),
                    TaskExtensionModel.category_id.in_(user.procurement_category_ids),
                )
                .exists()
            )
    for column, value in (
        (AuditLogModel.task_id, task_id),
        (AuditLogModel.action_type, action_type),
        (AuditLogModel.executor, executor),
        (AuditLogModel.business_object_type, business_object_type),
        (AuditLogModel.business_object_id, business_object_id),
    ):
        if value is not None:
            conditions.append(column == value)
    if start_time:
        conditions.append(AuditLogModel.created_at >= start_time)
    if end_time:
        conditions.append(AuditLogModel.created_at <= end_time)

    statement = (
        select(AuditLogModel)
        .where(*conditions)
        .order_by(AuditLogModel.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    async with forge_app.DATABASE.Session() as session:
        total = await session.scalar(select(func.count()).select_from(AuditLogModel).where(*conditions))
        logs = (await session.scalars(statement)).all()

    try:
        client = get_minio_client() if any(
            log.screenshot_before_key or log.screenshot_after_key for log in logs
        ) else None
    except RuntimeError:
        client = None

    items = [
        AuditLogResponse(
            audit_log_id=log.audit_log_id,
            task_id=log.task_id,
            organization_id=log.organization_id,
            department_id=log.department_id,
            business_line_id=log.business_line_id,
            business_object_type=log.business_object_type,
            business_object_id=log.business_object_id,
            action_index=log.action_index,
            action_type=log.action_type,
            target_element=log.target_element,
            input_value=log.input_value,
            page_url=log.page_url,
            screenshot_before_url=await _screenshot_url(client, log.screenshot_before_key, log.created_at),
            screenshot_after_url=await _screenshot_url(client, log.screenshot_after_key, log.created_at),
            duration_ms=log.duration_ms,
            executor=log.executor,
            execution_result=log.execution_result,
            error_message=log.error_message,
            has_approval=log.has_approval,
            approval_id=log.approval_id,
            approver_user_id=log.approver_user_id,
            created_at=log.created_at,
        )
        for log in logs
    ]
    return AuditLogListResponse(items=items, total=total or 0, page=page, page_size=page_size)


@router.post("/tasks/{task_id}/quote-files", response_model=QuoteFileResponse)
async def upload_quote_file(
    task_id: str,
    file: UploadFile = File(...),
    user: UserContext = Depends(require_any_operator),
) -> QuoteFileResponse:
    conditions = [
        TaskExtensionModel.task_id == task_id,
        TaskExtensionModel.organization_id == user.org_id,
    ]
    if not user.is_org_admin:
        conditions.extend((
            TaskExtensionModel.department_id.in_(_department_ids_for_role(user, "operator")),
            TaskExtensionModel.category_id.in_(user.procurement_category_ids),
        ))
    statement = (
        select(TaskExtensionModel)
        .join(
            TaskModel,
            (TaskModel.task_id == TaskExtensionModel.task_id)
            & (TaskModel.organization_id == TaskExtensionModel.organization_id),
        )
        .where(*conditions)
    )
    async with forge_app.DATABASE.Session() as session:
        extension = await session.scalar(statement)
    if extension is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Procurement task not found")

    data = await file.read(settings.MAX_UPLOAD_FILE_SIZE + 1)
    await file.close()
    if len(data) > settings.MAX_UPLOAD_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Quote file is too large")
    if file.content_type != "application/pdf" or not (file.filename or "").lower().endswith(".pdf") or not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only valid PDF quote files are allowed")

    bucket = get_bucket_name()
    object_key = generate_quote_object_key(user.org_id, task_id, file.filename or "quote.pdf")
    try:
        client = get_minio_client()
        object_uri = await upload_file(client, bucket, object_key, data, "application/pdf")
        artifact_id = generate_artifact_id()
        await forge_app.DATABASE.create_artifact(
            artifact_id,
            ArtifactType.PDF.value,
            object_uri,
            organization_id=user.org_id,
            task_id=task_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Quote file storage is unavailable") from exc
    try:
        presigned_url = await get_presigned_url(client, bucket, object_key)
    except Exception:
        presigned_url = None

    await record_audit_event(
        task_id=task_id,
        org_id=user.org_id,
        department_id=extension.department_id,
        business_line_id=extension.business_line_id,
        business_object_type="quote_file",
        business_object_id=artifact_id,
        action_index=3,
        action_type=ActionType.QUOTE_FILE_UPLOADED.value,
        executor=user.user_id,
        target_element="quote_file",
        input_value={"artifact_id": artifact_id, "content_type": "application/pdf", "size_bytes": len(data)},
    )
    return QuoteFileResponse(
        artifact_id=artifact_id,
        task_id=task_id,
        object_uri=object_uri,
        presigned_url=presigned_url,
    )
