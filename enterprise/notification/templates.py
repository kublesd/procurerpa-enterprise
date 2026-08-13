"""Non-sensitive procurement notification templates."""

from dataclasses import dataclass

RISK_EMOJI = {"high": "🟠", "critical": "🔴"}
RISK_LABEL_CN = {"high": "高风险", "critical": "严重风险"}


@dataclass(frozen=True)
class ApprovalNotificationContext:
    approval_id: str
    task_id: str
    risk_level: str
    department_name: str
    approval_url: str
    timeout_seconds: int
    organization_id: str | None = None
    department_id: str | None = None


@dataclass(frozen=True)
class OrderAnomalyNotificationContext:
    order_id: str
    anomaly_code: str
    order_url: str


def _timeout_display(seconds: int) -> str:
    return f"{seconds // 3600} 小时" if seconds >= 3600 else f"{seconds // 60} 分钟"


def render_markdown(ctx: ApprovalNotificationContext) -> str:
    emoji = RISK_EMOJI.get(ctx.risk_level, "⚪")
    label = RISK_LABEL_CN.get(ctx.risk_level, "待复核风险")
    return "\n".join(
        (
            f"### {emoji} 采购审批请求 — {label}",
            "",
            f"> **审批编号**: {ctx.approval_id}",
            f"> **关联任务**: {ctx.task_id}",
            f"> **所属部门**: {ctx.department_name}",
            "",
            f"⏱ 请在 **{_timeout_display(ctx.timeout_seconds)}** 内处理",
            f"[进入审批中心]({ctx.approval_url})",
        )
    )


def render_wecom_payload(ctx: ApprovalNotificationContext) -> dict:
    return {"msgtype": "markdown", "markdown": {"content": render_markdown(ctx)}}


def render_dingtalk_payload(ctx: ApprovalNotificationContext) -> dict:
    title = f"{RISK_EMOJI.get(ctx.risk_level, '⚪')} 采购审批请求"
    return {
        "msgtype": "actionCard",
        "actionCard": {
            "title": title,
            "text": render_markdown(ctx),
            "singleTitle": "进入审批中心",
            "singleURL": ctx.approval_url,
        },
    }


def render_order_wecom_payload(ctx: OrderAnomalyNotificationContext) -> dict:
    content = "\n".join(
        (
            "### ⚠️ 采购订单异常",
            "",
            f"> **订单编号**: {ctx.order_id}",
            f"> **异常类型**: {ctx.anomaly_code}",
            f"[查看订单]({ctx.order_url})",
        )
    )
    return {"msgtype": "markdown", "markdown": {"content": content}}


def render_order_dingtalk_payload(ctx: OrderAnomalyNotificationContext) -> dict:
    content = render_order_wecom_payload(ctx)["markdown"]["content"]
    return {
        "msgtype": "actionCard",
        "actionCard": {
            "title": "⚠️ 采购订单异常",
            "text": content,
            "singleTitle": "查看订单",
            "singleURL": ctx.order_url,
        },
    }
