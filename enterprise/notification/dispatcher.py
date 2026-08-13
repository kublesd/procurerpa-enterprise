"""Best-effort approval notification dispatch with channel fallback."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import SecretStr

from enterprise.audit.logger import record_audit_event
from enterprise.audit.models import ActionType
from skyvern.config import settings

from .channels import SendResult, send_dingtalk, send_wecom
from .templates import ApprovalNotificationContext, render_dingtalk_payload, render_wecom_payload

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookConfig:
    wecom_url: str | None = None
    dingtalk_url: str | None = None


@dataclass(frozen=True)
class NotificationAttempt:
    event_id: str
    channel: str
    success: bool
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class DispatchResult:
    event_id: str
    attempts: list[NotificationAttempt] = field(default_factory=list)

    @property
    def total_success(self) -> int:
        return sum(attempt.success for attempt in self.attempts)

    @property
    def total_failed(self) -> int:
        return sum(not attempt.success for attempt in self.attempts)


def _attempt(event_id: str, result: SendResult) -> NotificationAttempt:
    return NotificationAttempt(event_id, result.channel, result.success, result.error)


async def dispatch_notifications(
    ctx: ApprovalNotificationContext,
    config: WebhookConfig,
) -> DispatchResult:
    result = DispatchResult(ctx.approval_id)
    if config.wecom_url:
        sent = await send_wecom(config.wecom_url, render_wecom_payload(ctx))
        result.attempts.append(_attempt(ctx.approval_id, sent))
        if sent.success:
            return result
    if config.dingtalk_url:
        sent = await send_dingtalk(config.dingtalk_url, render_dingtalk_payload(ctx))
        result.attempts.append(_attempt(ctx.approval_id, sent))
    return result


def _secret_value(value: SecretStr | None) -> str | None:
    if value is None:
        return None
    return value.get_secret_value().strip() or None


async def notify_approval_created(ctx: ApprovalNotificationContext) -> DispatchResult:
    """Send after approval commit; notification failures never escape to the business flow."""
    result = DispatchResult(ctx.approval_id)
    try:
        result = await dispatch_notifications(
            ctx,
            WebhookConfig(
                wecom_url=_secret_value(settings.WECOM_WEBHOOK_URL),
                dingtalk_url=_secret_value(settings.DINGTALK_WEBHOOK_URL),
            ),
        )
        for attempt in result.attempts:
            logger.info(
                "approval notification approval_id=%s channel=%s success=%s error=%s",
                attempt.event_id,
                attempt.channel,
                attempt.success,
                attempt.error,
            )
        if not result.attempts:
            logger.info("approval notification skipped approval_id=%s reason=not_configured", ctx.approval_id)
    except Exception as exc:
        logger.warning(
            "approval notification failed approval_id=%s error_type=%s",
            ctx.approval_id,
            type(exc).__name__,
        )
    if ctx.organization_id and ctx.department_id:
        await record_audit_event(
            task_id=ctx.task_id,
            org_id=ctx.organization_id,
            department_id=ctx.department_id,
            business_object_type="approval",
            business_object_id=ctx.approval_id,
            action_index=3,
            action_type=ActionType.NOTIFICATION_SENT.value,
            executor="system",
            input_value={
                "attempts": [
                    {"channel": attempt.channel, "success": attempt.success, "error": attempt.error}
                    for attempt in result.attempts
                ]
            },
            execution_result=(
                "success" if result.total_success else "failed" if result.attempts else "skipped"
            ),
            has_approval=True,
            approval_id=ctx.approval_id,
        )
    return result
