"""Procurement risk keywords and fixed deterministic thresholds."""

import re
from dataclasses import dataclass
from decimal import Decimal

RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

MEDIUM_AMOUNT_CNY = Decimal("50000")
HIGH_AMOUNT_CNY = Decimal("100000")
CRITICAL_AMOUNT_CNY = Decimal("1000000")

HIGH_QUOTE_DEVIATION = Decimal("0.20")
CRITICAL_QUOTE_DEVIATION = Decimal("0.50")

OPERATION_RISKS = {
    "single_source": ("high", "Single-source procurement requires additional review"),
    "emergency": ("high", "Emergency procurement bypasses the standard lead time"),
    "advance_payment": ("critical", "Advance payment exposes funds before delivery"),
    "supplier_bank_change": ("critical", "Supplier bank-account change requires independent verification"),
}
ALLOWED_OPERATION_TYPES = {"standard", *OPERATION_RISKS}


@dataclass(frozen=True)
class ProcurementRiskKeyword:
    keyword: str
    risk_level: str
    category: str
    reason: str


PROCUREMENT_RISK_KEYWORDS = (
    ProcurementRiskKeyword("供应商资质", "high", "supplier_qualification", "Supplier qualification needs review"),
    ProcurementRiskKeyword("资质过期", "critical", "supplier_qualification", "Supplier qualification is expired"),
    ProcurementRiskKeyword("unqualified supplier", "critical", "supplier_qualification", "Supplier is not qualified"),
    ProcurementRiskKeyword("single source", "high", "single_source", "Single-source procurement needs additional review"),
    ProcurementRiskKeyword("单一来源", "high", "single_source", "Single-source procurement needs additional review"),
    ProcurementRiskKeyword("异常报价", "high", "quote_anomaly", "Abnormal supplier quote needs review"),
    ProcurementRiskKeyword("报价异常", "high", "quote_anomaly", "Abnormal supplier quote needs review"),
    ProcurementRiskKeyword("abnormal quote", "high", "quote_anomaly", "Abnormal supplier quote needs review"),
    ProcurementRiskKeyword("合同条款", "high", "contract_payment", "Contract terms need procurement review"),
    ProcurementRiskKeyword("合同/付款", "high", "contract_payment", "Contract and payment terms need review"),
    ProcurementRiskKeyword("付款", "high", "contract_payment", "Payment terms need procurement review"),
    ProcurementRiskKeyword("payment", "high", "contract_payment", "Payment terms need procurement review"),
    ProcurementRiskKeyword("预付款", "critical", "contract_payment", "Advance payment exposes funds before delivery"),
    ProcurementRiskKeyword("advance payment", "critical", "contract_payment", "Advance payment exposes funds before delivery"),
    ProcurementRiskKeyword("银行账户变更", "critical", "supplier_bank_change", "Supplier bank-account change needs independent verification"),
    ProcurementRiskKeyword("supplier bank account change", "critical", "supplier_bank_change", "Supplier bank-account change needs independent verification"),
    ProcurementRiskKeyword("敏感品类", "high", "sensitive_category", "Sensitive procurement category needs additional review"),
    ProcurementRiskKeyword("sensitive category", "high", "sensitive_category", "Sensitive procurement category needs additional review"),
    ProcurementRiskKeyword("大额采购", "high", "large_procurement", "Large procurement needs additional review"),
    ProcurementRiskKeyword("large procurement", "high", "large_procurement", "Large procurement needs additional review"),
    ProcurementRiskKeyword("紧急采购", "high", "emergency_procurement", "Emergency procurement bypasses standard lead time"),
    ProcurementRiskKeyword("emergency procurement", "high", "emergency_procurement", "Emergency procurement bypasses standard lead time"),
    ProcurementRiskKeyword("urgent exception", "high", "emergency_procurement", "Urgent procurement exception needs review"),
    ProcurementRiskKeyword("绕过审批", "critical", "approval_bypass", "Approval bypass is not allowed for procurement"),
    ProcurementRiskKeyword("bypass approval", "critical", "approval_bypass", "Approval bypass is not allowed for procurement"),
)

_TEXT_AMOUNT_PATTERN = re.compile(
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>亿|万|billion|million|人民币|元|cny|rmb)",
    re.IGNORECASE,
)


def find_procurement_risk_keywords(text: str) -> list[ProcurementRiskKeyword]:
    """Return matching procurement indicators in stable declaration order."""
    lowered = text.lower()
    return [entry for entry in PROCUREMENT_RISK_KEYWORDS if entry.keyword.lower() in lowered]


def amount_risk_from_text(text: str) -> tuple[Decimal, str] | None:
    """Parse explicit currency amounts from redacted procurement text."""
    multipliers = {
        "亿": Decimal("100000000"),
        "万": Decimal("10000"),
        "billion": Decimal("1000000000"),
        "million": Decimal("1000000"),
        "人民币": Decimal("1"),
        "元": Decimal("1"),
        "cny": Decimal("1"),
        "rmb": Decimal("1"),
    }
    amount = None
    for match in _TEXT_AMOUNT_PATTERN.finditer(text):
        value = Decimal(match.group("value").replace(",", "")) * multipliers[match.group("unit").lower()]
        amount = value if amount is None else max(amount, value)
    if amount is None:
        return None
    if amount >= CRITICAL_AMOUNT_CNY:
        return amount, "critical"
    if amount >= HIGH_AMOUNT_CNY:
        return amount, "high"
    if amount >= MEDIUM_AMOUNT_CNY:
        return amount, "medium"
    return None
