"""Explainable procurement-risk detection with optional redacted LLM review."""

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable

import structlog

from .risk_keywords import (
    ALLOWED_OPERATION_TYPES,
    CRITICAL_AMOUNT_CNY,
    CRITICAL_QUOTE_DEVIATION,
    HIGH_AMOUNT_CNY,
    HIGH_QUOTE_DEVIATION,
    MEDIUM_AMOUNT_CNY,
    OPERATION_RISKS,
    RISK_ORDER,
    amount_risk_from_text,
    find_procurement_risk_keywords,
)

LOG = structlog.get_logger()
LLMCallable = Callable[[str], Awaitable[dict | None]]


def _decimal(value: Decimal | str | int | float | None, name: str) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a valid decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True)
class RiskContext:
    """Structured procurement inputs; only ``redacted_description`` may reach an LLM."""

    total_amount_cny: Decimal
    supplier_id: str | None
    is_new_supplier: bool = False
    supplier_qualified: bool | None = None
    selected_quote_cny: Decimal | None = None
    average_quote_cny: Decimal | None = None
    operation_type: str = "standard"
    tax_rate: Decimal | None = None
    redacted_description: str | None = None

    def __post_init__(self) -> None:
        for name in ("total_amount_cny", "selected_quote_cny", "average_quote_cny", "tax_rate"):
            object.__setattr__(self, name, _decimal(getattr(self, name), name))
        if self.total_amount_cny < 0:
            raise ValueError("total_amount_cny must not be negative")
        if self.selected_quote_cny is not None and self.selected_quote_cny < 0:
            raise ValueError("selected_quote_cny must not be negative")
        if self.average_quote_cny is not None and self.average_quote_cny <= 0:
            raise ValueError("average_quote_cny must be greater than zero")
        if self.tax_rate is not None and not Decimal("0") <= self.tax_rate <= Decimal("1"):
            raise ValueError("tax_rate must be between 0 and 1")
        if self.operation_type not in ALLOWED_OPERATION_TYPES:
            raise ValueError(f"unsupported operation_type: {self.operation_type}")


@dataclass(frozen=True)
class RiskFinding:
    category: str
    risk_level: str
    reason: str


@dataclass
class RiskAssessment:
    risk_level: str
    reason: str
    deterministic_level: str
    findings: list[RiskFinding] = field(default_factory=list)
    stage: str = "deterministic"
    llm_fallback: bool = False
    matched_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "risk_level": self.risk_level,
            "deterministic_level": self.deterministic_level,
            "reason": self.reason,
            "findings": [asdict(finding) for finding in self.findings],
            "stage": self.stage,
            "llm_fallback": self.llm_fallback,
            "matched_keywords": self.matched_keywords,
        }


def _evaluate(context: RiskContext) -> list[RiskFinding]:
    findings: list[RiskFinding] = []

    if context.total_amount_cny >= CRITICAL_AMOUNT_CNY:
        findings.append(RiskFinding("amount", "critical", "Purchase amount reached the critical CNY threshold"))
    elif context.total_amount_cny >= HIGH_AMOUNT_CNY:
        findings.append(RiskFinding("amount", "high", "Purchase amount reached the high CNY threshold"))
    elif context.total_amount_cny >= MEDIUM_AMOUNT_CNY:
        findings.append(RiskFinding("amount", "medium", "Purchase amount reached the review CNY threshold"))

    if not context.supplier_id:
        findings.append(RiskFinding("supplier", "medium", "Supplier identity is missing"))
    elif context.is_new_supplier:
        findings.append(RiskFinding("supplier", "high", "Supplier has no completed procurement history"))

    if context.supplier_qualified is False:
        findings.append(RiskFinding("qualification", "critical", "Supplier qualification is invalid or expired"))
    elif context.supplier_qualified is None:
        findings.append(RiskFinding("qualification", "medium", "Supplier qualification has not been verified"))

    if context.selected_quote_cny is None or context.average_quote_cny is None:
        findings.append(RiskFinding("quote_deviation", "medium", "Comparable quote data is incomplete"))
    else:
        deviation = abs(context.selected_quote_cny - context.average_quote_cny) / context.average_quote_cny
        if deviation >= CRITICAL_QUOTE_DEVIATION:
            findings.append(RiskFinding("quote_deviation", "critical", "Selected quote deviates at least 50% from average"))
        elif deviation >= HIGH_QUOTE_DEVIATION:
            findings.append(RiskFinding("quote_deviation", "high", "Selected quote deviates at least 20% from average"))

    if operation_risk := OPERATION_RISKS.get(context.operation_type):
        findings.append(RiskFinding("operation_type", operation_risk[0], operation_risk[1]))

    if context.redacted_description:
        for keyword in find_procurement_risk_keywords(context.redacted_description):
            findings.append(RiskFinding(keyword.category, keyword.risk_level, keyword.reason))
        if text_amount := amount_risk_from_text(context.redacted_description):
            _, level = text_amount
            findings.append(RiskFinding("amount", level, f"Redacted procurement text contains a {level}-risk CNY amount"))

    return findings


async def detect_risk(context: RiskContext, llm_callable: LLMCallable | None = None) -> RiskAssessment:
    """Evaluate procurement rules, then optionally escalate a hit to Stage 2."""
    findings = _evaluate(context)
    deterministic_level = max((finding.risk_level for finding in findings), key=RISK_ORDER.get, default="low")
    reason = "; ".join(finding.reason for finding in findings) or "No procurement risk indicators detected"
    matched_keywords = [
        entry.keyword for entry in find_procurement_risk_keywords(context.redacted_description or "")
    ]
    assessment = RiskAssessment(
        deterministic_level,
        reason,
        deterministic_level,
        findings,
        matched_keywords=matched_keywords,
    )

    if llm_callable is None or not context.redacted_description or not findings:
        return assessment

    prompt = (
        "You are a procurement operations and procurement compliance reviewer. "
        "Review this already-redacted procurement description for additional risk. "
        "Never lower the deterministic result. Return one JSON object with "
        '"risk_level" (low|medium|high|critical) and "reason".\n'
        f"Deterministic level: {deterministic_level}\n"
        f"Triggered categories: {', '.join(finding.category for finding in findings) or 'none'}\n"
        f"Matched procurement keywords: {', '.join(matched_keywords) or 'none'}\n"
        f"Redacted procurement description: {context.redacted_description}"
    )
    try:
        result = await llm_callable(prompt)
        if not isinstance(result, dict) or result.get("risk_level") not in RISK_ORDER:
            assessment.llm_fallback = True
            if RISK_ORDER[assessment.risk_level] < RISK_ORDER["high"]:
                assessment.risk_level = "high"
                assessment.reason = "Stage 2 procurement review returned invalid output; conservative high-risk fallback applied"
            return assessment
        level = result["risk_level"]
        llm_reason = result.get("reason")
        assessment.stage = "llm"
        if RISK_ORDER[level] >= RISK_ORDER[deterministic_level]:
            assessment.risk_level = level
            assessment.reason = str(llm_reason or "LLM identified additional redacted procurement risk")
        return assessment
    except Exception as exc:
        LOG.warning("procurement risk LLM review failed", error_type=type(exc).__name__)
        assessment.llm_fallback = True
        if RISK_ORDER[assessment.risk_level] < RISK_ORDER["high"]:
            assessment.risk_level = "high"
            assessment.reason = "Stage 2 procurement review failed; conservative high-risk fallback applied"
        return assessment
