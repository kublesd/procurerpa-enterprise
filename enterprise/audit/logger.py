"""Best-effort database audit writer."""

import json
import logging
from typing import Any

from skyvern.forge import app as forge_app

from .models import AuditLogModel, generate_audit_log_id
from .sanitizer import hash_raw_value, sanitize_input, sanitize_payload

logger = logging.getLogger(__name__)


def _serialized_details(value: Any) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    sanitized = sanitize_payload(value)
    stored = sanitized if isinstance(sanitized, str) else json.dumps(
        sanitized, ensure_ascii=False, sort_keys=True, default=str
    )
    return stored, hash_raw_value(raw)


async def write_audit_log(
    db_session,
    task_id: str,
    org_id: str,
    department_id: str,
    action_index: int,
    action_type: str,
    executor: str,
    business_line_id: str | None = None,
    business_object_type: str | None = None,
    business_object_id: str | None = None,
    target_element: str | None = None,
    input_value: Any = None,
    page_url: str | None = None,
    screenshot_before_key: str | None = None,
    screenshot_after_key: str | None = None,
    duration_ms: int | None = None,
    execution_result: str = "success",
    error_message: str | None = None,
    has_approval: bool = False,
    approval_id: str | None = None,
    approver_user_id: str | None = None,
) -> AuditLogModel | None:
    """Persist one sanitized event; audit failures never break procurement."""
    try:
        stored_value, raw_hash = _serialized_details(input_value)
        entry = AuditLogModel(
            audit_log_id=generate_audit_log_id(),
            task_id=task_id,
            organization_id=org_id,
            department_id=department_id,
            business_line_id=business_line_id,
            business_object_type=business_object_type,
            business_object_id=business_object_id,
            action_index=action_index,
            action_type=action_type,
            target_element=sanitize_input(target_element),
            input_value=stored_value,
            input_value_raw_hash=raw_hash,
            page_url=sanitize_input(page_url),
            screenshot_before_key=screenshot_before_key,
            screenshot_after_key=screenshot_after_key,
            duration_ms=duration_ms,
            executor=executor,
            execution_result=execution_result,
            error_message=sanitize_input(error_message),
            has_approval=has_approval,
            approval_id=approval_id,
            approver_user_id=approver_user_id,
        )
        db_session.add(entry)
        await db_session.commit()
        return entry
    except Exception as exc:
        logger.warning(
            "AUDIT_LOG_FAILURE task=%s action=%d error_type=%s",
            task_id,
            action_index,
            type(exc).__name__,
        )
        try:
            await db_session.rollback()
        except Exception:
            pass
        return None


async def record_audit_event(**kwargs) -> AuditLogModel | None:
    """Open an isolated transaction so audit rollback cannot undo business data."""
    try:
        async with forge_app.DATABASE.Session() as session:
            return await write_audit_log(session, **kwargs)
    except Exception as exc:
        logger.warning(
            "AUDIT_LOG_FAILURE task=%s action=%s error_type=%s",
            kwargs.get("task_id"),
            kwargs.get("action_index"),
            type(exc).__name__,
        )
        return None
