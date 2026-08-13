"""Enterprise WeCom and DingTalk webhook adapters."""

import logging
from dataclasses import dataclass
from enum import Enum

import httpx

logger = logging.getLogger(__name__)
WEBHOOK_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


class ChannelType(str, Enum):
    WECOM = "wecom"
    DINGTALK = "dingtalk"


@dataclass(frozen=True)
class SendResult:
    success: bool
    channel: str
    status_code: int | None = None
    error: str | None = None


async def _send(channel: ChannelType, webhook_url: str, payload: dict) -> SendResult:
    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            response = await client.post(webhook_url, json=payload)
        if response.status_code != 200:
            return SendResult(False, channel.value, response.status_code, f"http_{response.status_code}")
        try:
            data = response.json()
        except ValueError:
            return SendResult(False, channel.value, response.status_code, "invalid_response")
        if data.get("errcode") == 0:
            return SendResult(True, channel.value, response.status_code)
        return SendResult(False, channel.value, response.status_code, "api_error")
    except httpx.TimeoutException:
        logger.warning("%s webhook timed out", channel.value)
        return SendResult(False, channel.value, error="timeout")
    except httpx.HTTPError as exc:
        logger.warning("%s webhook request failed: %s", channel.value, type(exc).__name__)
        return SendResult(False, channel.value, error="request_failed")
    except Exception as exc:
        logger.warning("%s webhook failed: %s", channel.value, type(exc).__name__)
        return SendResult(False, channel.value, error="internal_error")


async def send_wecom(webhook_url: str, payload: dict) -> SendResult:
    return await _send(ChannelType.WECOM, webhook_url, payload)


async def send_dingtalk(webhook_url: str, payload: dict) -> SendResult:
    return await _send(ChannelType.DINGTALK, webhook_url, payload)
