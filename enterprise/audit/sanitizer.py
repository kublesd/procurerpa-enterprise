"""Sanitize procurement audit values before persistence."""

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

_PASSWORD = re.compile(r"((?:password|passwd|pwd|密码|口令)\s*[:=：]\s*)\S+", re.IGNORECASE)
_TOKEN = re.compile(r"((?:access_token|token|secret|key)\s*[=:]\s*)[^&\s]+", re.IGNORECASE)
_AUTHORIZATION = re.compile(
    r"(authorization\s*[:=]\s*)(?:[A-Za-z][\w-]*\s+)?[^\s,;]+",
    re.IGNORECASE,
)
_AUTH_SCHEME = re.compile(r"((?:bearer|basic)\s+)[^\s,;]+", re.IGNORECASE)
_URL_QUERY = re.compile(r"(https?://[^\s?]+)\?[^\s,;]+", re.IGNORECASE)
_ID_NUMBER = re.compile(
    r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b"
)
_CARD_NUMBER = re.compile(r"\b[3-6]\d{3}(?:[\s-]?\d{4}){3}\b")
_LONG_ACCOUNT = re.compile(r"(?<!\d)\d(?:[\s-]?\d){15,29}(?!\d)")
_PHONE = re.compile(r"\b1[3-9]\d{9}\b")
_BANK_LABEL = re.compile(
    r"((?:supplier\s*)?(?:bank\s*)?account(?:\s*(?:number|no))?|银行账号|银行账户)\s*[:=：]\s*([0-9 -]{8,40})",
    re.IGNORECASE,
)

_SECRET_KEYS = ("password", "passwd", "pwd", "token", "secret", "authorization", "webhook")
_BANK_KEYS = ("bankaccount", "bank_account", "accountnumber", "account_number", "银行账号", "银行账户")
_QUOTE_KEYS = ("quote", "报价")


def _mask_digits(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return "****" if len(digits) <= 4 else "*" * (len(digits) - 4) + digits[-4:]


def sanitize_input(value: str | None) -> str | None:
    """Mask secrets embedded in free text while preserving business amounts."""
    if value is None:
        return None
    result = _PASSWORD.sub(r"\1********", value)
    result = _TOKEN.sub(r"\1********", result)
    result = _AUTHORIZATION.sub(r"\1********", result)
    result = _AUTH_SCHEME.sub(r"\1********", result)
    result = _BANK_LABEL.sub(lambda match: f"{match.group(1)}: {_mask_digits(match.group(2))}", result)
    result = _ID_NUMBER.sub(lambda match: _mask_digits(match.group(0)), result)
    result = _CARD_NUMBER.sub(lambda match: _mask_digits(match.group(0)), result)
    result = _LONG_ACCOUNT.sub(lambda match: _mask_digits(match.group(0)), result)
    result = _PHONE.sub(lambda match: f"{match.group(0)[:3]}****{match.group(0)[-4:]}", result)
    return _URL_QUERY.sub(r"\1?[redacted]", result)


def sanitize_payload(value: Any, field_name: str = "") -> Any:
    """Recursively sanitize structured audit details using their field names."""
    normalized = re.sub(r"[^a-z0-9_\u4e00-\u9fff]", "", field_name.lower())
    if any(key in normalized for key in _SECRET_KEYS):
        return "********"
    if any(key in normalized for key in _BANK_KEYS):
        return _mask_digits(str(value))
    if any(key in normalized for key in _QUOTE_KEYS):
        return "********"
    if isinstance(value, Mapping):
        return {str(key): sanitize_payload(item, str(key)) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_payload(item) for item in value]
    return sanitize_input(value) if isinstance(value, str) else value


def hash_raw_value(value: str | None) -> str | None:
    """Keep a one-way integrity fingerprint without storing the raw value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value is not None else None
