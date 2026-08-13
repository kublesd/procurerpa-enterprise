"""Decimal normalization and deterministic supplier-quote comparison."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MONEY_QUANTUM = Decimal("0.01")
QUANTITY_QUANTUM = Decimal("0.000001")
LANDED_UNIT_QUANTUM = Decimal("0.000001")


def _decimal(value: Decimal | str | int) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("quote amount must be a valid decimal") from exc
    if not result.is_finite():
        raise ValueError("quote amount must be finite")
    return result


def normalize_money(value: Decimal | str | int) -> Decimal:
    """Normalize CNY values to cents without converting through float."""

    return _decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def normalize_quantity(value: Decimal | str | int) -> Decimal:
    """Normalize the single supported base quantity unit to six decimals."""

    return _decimal(value).quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class QuoteComparisonItem:
    quote_id: str
    supplier_id: str
    total_cny: Decimal
    landed_unit_price_cny: Decimal
    delivery_days: int
    eligible: bool
    rank: int | None
    reason: str


@dataclass(frozen=True)
class QuoteComparisonResult:
    quotes: tuple[QuoteComparisonItem, ...]
    recommended_quote_id: str | None
    recommendation_reason: str


def compare_quotes(quotes: Iterable[object]) -> QuoteComparisonResult:
    """Rank quotes by landed unit price with stable deterministic tie-breakers."""

    items: list[QuoteComparisonItem] = []
    for quote in quotes:
        quantity = normalize_quantity(getattr(quote, "quantity"))
        moq = normalize_quantity(getattr(quote, "moq"))
        unit_price = normalize_money(getattr(quote, "unit_price_cny"))
        freight = normalize_money(getattr(quote, "freight_cny"))
        total = normalize_money(unit_price * quantity + freight)
        landed_unit_price = (total / quantity).quantize(LANDED_UNIT_QUANTUM, rounding=ROUND_HALF_UP)
        eligible = quantity >= moq
        items.append(
            QuoteComparisonItem(
                quote_id=str(getattr(quote, "quote_id")),
                supplier_id=str(getattr(quote, "supplier_id")),
                total_cny=total,
                landed_unit_price_cny=landed_unit_price,
                delivery_days=int(getattr(quote, "delivery_days")),
                eligible=eligible,
                rank=None,
                reason=(
                    "Eligible"
                    if eligible
                    else "Requested quantity is below the supplier minimum order quantity"
                ),
            )
        )

    items.sort(
        key=lambda item: (
            not item.eligible,
            item.landed_unit_price_cny,
            item.delivery_days,
            item.supplier_id,
            item.quote_id,
        )
    )
    ranked: list[QuoteComparisonItem] = []
    rank = 0
    for item in items:
        if item.eligible:
            rank += 1
            ranked.append(replace(item, rank=rank))
        else:
            ranked.append(item)

    eligible = [item for item in ranked if item.eligible]
    if not eligible:
        return QuoteComparisonResult(
            quotes=tuple(ranked),
            recommended_quote_id=None,
            recommendation_reason="No quote meets the requested quantity and minimum order quantity.",
        )
    return QuoteComparisonResult(
        quotes=tuple(ranked),
        recommended_quote_id=eligible[0].quote_id,
        recommendation_reason=(
            "Lowest tax-inclusive landed unit price; delivery days, supplier ID, and quote ID break ties deterministically."
        ),
    )
