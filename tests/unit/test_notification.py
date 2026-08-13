"""Day 7 procurement notification checks."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from enterprise.notification.channels import SendResult, send_dingtalk, send_wecom
from enterprise.notification.dispatcher import (
    DispatchResult,
    NotificationAttempt,
    WebhookConfig,
    dispatch_notifications,
    notify_approval_created,
)
from enterprise.notification.templates import (
    ApprovalNotificationContext,
    OrderAnomalyNotificationContext,
    render_dingtalk_payload,
    render_order_dingtalk_payload,
    render_order_wecom_payload,
    render_wecom_payload,
)


def _approval() -> ApprovalNotificationContext:
    return ApprovalNotificationContext(
        approval_id="apr_001",
        task_id="task_001",
        risk_level="critical",
        department_name="采购部",
        approval_url="https://app.example.com/enterprise/approvals",
        timeout_seconds=1800,
    )


def _http_client(response: MagicMock | None = None, error: Exception | None = None) -> AsyncMock:
    client = AsyncMock()
    client.post.return_value = response
    client.post.side_effect = error
    client.__aenter__.return_value = client
    client.__aexit__.return_value = False
    return client


def test_approval_templates_contain_only_redacted_summary() -> None:
    wecom = render_wecom_payload(_approval())
    dingtalk = render_dingtalk_payload(_approval())
    content = wecom["markdown"]["content"]

    assert wecom["msgtype"] == "markdown"
    assert dingtalk["msgtype"] == "actionCard"
    assert "apr_001" in content
    assert "task_001" in content
    assert "采购部" in content
    assert "30 分钟" in content
    assert dingtalk["actionCard"]["singleURL"].endswith("/enterprise/approvals")
    with pytest.raises(TypeError):
        ApprovalNotificationContext(**{**_approval().__dict__, "supplier_bank_account": "secret"})


def test_order_anomaly_templates_are_available_for_order_service() -> None:
    ctx = OrderAnomalyNotificationContext(
        order_id="po_001",
        anomaly_code="delivery_overdue",
        order_url="https://app.example.com/orders/po_001",
    )

    assert "delivery_overdue" in render_order_wecom_payload(ctx)["markdown"]["content"]
    assert render_order_dingtalk_payload(ctx)["actionCard"]["singleURL"].endswith("/orders/po_001")


@pytest.mark.asyncio
@patch("enterprise.notification.channels.httpx.AsyncClient")
async def test_wecom_success(mock_client_class) -> None:
    response = MagicMock(status_code=200)
    response.json.return_value = {"errcode": 0, "errmsg": "ok"}
    mock_client_class.return_value = _http_client(response)

    result = await send_wecom("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret", {})

    assert result == SendResult(True, "wecom", 200)


@pytest.mark.asyncio
@patch("enterprise.notification.channels.httpx.AsyncClient")
async def test_dingtalk_success(mock_client_class) -> None:
    response = MagicMock(status_code=200)
    response.json.return_value = {"errcode": 0, "errmsg": "ok"}
    mock_client_class.return_value = _http_client(response)

    result = await send_dingtalk("https://oapi.dingtalk.com/robot/send?access_token=secret", {})

    assert result == SendResult(True, "dingtalk", 200)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 500])
@patch("enterprise.notification.channels.httpx.AsyncClient")
async def test_channel_http_error(mock_client_class, status_code: int) -> None:
    response = MagicMock(status_code=status_code)
    mock_client_class.return_value = _http_client(response)

    result = await send_dingtalk("https://oapi.dingtalk.com/robot/send?access_token=secret", {})

    assert result.success is False
    assert result.error == f"http_{status_code}"


@pytest.mark.asyncio
@patch("enterprise.notification.channels.httpx.AsyncClient")
async def test_channel_api_error_is_sanitized(mock_client_class) -> None:
    response = MagicMock(status_code=200)
    response.json.return_value = {"errcode": 310000, "errmsg": "secret webhook rejected"}
    mock_client_class.return_value = _http_client(response)

    result = await send_dingtalk("https://oapi.dingtalk.com/robot/send?access_token=secret", {})

    assert result.error == "api_error"
    assert "secret" not in repr(result)


@pytest.mark.asyncio
@patch("enterprise.notification.channels.httpx.AsyncClient")
async def test_channel_timeout_is_sanitized(mock_client_class) -> None:
    mock_client_class.return_value = _http_client(error=httpx.TimeoutException("secret webhook timed out"))

    result = await send_wecom("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=secret", {})

    assert result.error == "timeout"
    assert "secret" not in repr(result)


@pytest.mark.asyncio
@patch("enterprise.notification.dispatcher.send_dingtalk")
@patch("enterprise.notification.dispatcher.send_wecom")
async def test_wecom_failure_falls_back_to_dingtalk(mock_wecom, mock_dingtalk) -> None:
    mock_wecom.return_value = SendResult(False, "wecom", error="timeout")
    mock_dingtalk.return_value = SendResult(True, "dingtalk", 200)

    result = await dispatch_notifications(
        _approval(),
        WebhookConfig("https://wecom.example", "https://dingtalk.example"),
    )

    assert [(attempt.channel, attempt.success) for attempt in result.attempts] == [
        ("wecom", False),
        ("dingtalk", True),
    ]


@pytest.mark.asyncio
@patch("enterprise.notification.dispatcher.send_dingtalk")
async def test_dingtalk_only_configuration(mock_dingtalk) -> None:
    mock_dingtalk.return_value = SendResult(True, "dingtalk", 200)

    result = await dispatch_notifications(_approval(), WebhookConfig(dingtalk_url="https://dingtalk.example"))

    assert result.total_success == 1


@pytest.mark.asyncio
async def test_notification_failure_never_escapes_business_flow(monkeypatch, caplog) -> None:
    async def fail(*_args, **_kwargs):
        raise RuntimeError("webhook-secret")

    monkeypatch.setattr("enterprise.notification.dispatcher.dispatch_notifications", fail)

    result = await notify_approval_created(_approval())

    assert result.event_id == "apr_001"
    assert result.attempts == []
    assert "webhook-secret" not in caplog.text


@pytest.mark.asyncio
async def test_notification_result_is_audited_without_webhook_secrets(monkeypatch) -> None:
    async def sent(*_args, **_kwargs):
        return DispatchResult("apr_001", [NotificationAttempt("apr_001", "wecom", True)])

    audit = AsyncMock()
    monkeypatch.setattr("enterprise.notification.dispatcher.dispatch_notifications", sent)
    monkeypatch.setattr("enterprise.notification.dispatcher.record_audit_event", audit)
    ctx = ApprovalNotificationContext(**{
        **_approval().__dict__,
        "organization_id": "org_1",
        "department_id": "dept_1",
    })

    await notify_approval_created(ctx)

    assert audit.await_args.kwargs["action_type"] == "notification_sent"
    assert audit.await_args.kwargs["input_value"]["attempts"] == [
        {"channel": "wecom", "success": True, "error": None}
    ]
