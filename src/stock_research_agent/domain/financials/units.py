"""Exact unit scaling and currency compatibility policies."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from stock_research_agent.domain.financials.enums import UnitType


class ReportedUnit(StrEnum):
    ONE = "ONE"
    THOUSAND = "THOUSAND"
    MILLION = "MILLION"
    BILLION = "BILLION"
    PER_SHARE = "PER_SHARE"
    SHARES = "SHARES"
    PERCENT = "PERCENT"
    RATIO = "RATIO"


class UnitNormalizationBlocked(ValueError):
    """The source unit or currency cannot be used without guessing."""


@dataclass(frozen=True)
class UnitNormalizationResult:
    original_value: Decimal
    original_unit: ReportedUnit
    normalized_value: Decimal
    normalized_unit: str
    scale_factor: Decimal


_AMOUNT_SCALES = {
    ReportedUnit.ONE: Decimal("1"),
    ReportedUnit.THOUSAND: Decimal("1000"),
    ReportedUnit.MILLION: Decimal("1000000"),
    ReportedUnit.BILLION: Decimal("1000000000"),
}


def normalize_unit(
    value: Decimal,
    reported_unit: ReportedUnit,
    expected_unit_type: UnitType,
) -> UnitNormalizationResult:
    """Normalize a declared source unit without rounding or currency conversion."""

    if not isinstance(value, Decimal):
        raise TypeError("financial values must be Decimal, never binary float")
    if not value.is_finite():
        raise UnitNormalizationBlocked("financial Decimal value must be finite")
    try:
        unit = ReportedUnit(reported_unit)
    except ValueError:
        raise UnitNormalizationBlocked(f"unknown unit: {reported_unit!r}") from None

    if expected_unit_type is UnitType.MONETARY_AMOUNT and unit in _AMOUNT_SCALES:
        scale = _AMOUNT_SCALES[unit]
        normalized_unit = ReportedUnit.ONE.value
    elif expected_unit_type is UnitType.PER_SHARE and unit is ReportedUnit.PER_SHARE:
        scale = Decimal("1")
        normalized_unit = ReportedUnit.PER_SHARE.value
    elif expected_unit_type is UnitType.SHARES and unit is ReportedUnit.SHARES:
        scale = Decimal("1")
        normalized_unit = ReportedUnit.SHARES.value
    elif expected_unit_type is UnitType.RATIO and unit is ReportedUnit.PERCENT:
        scale = Decimal("0.01")
        normalized_unit = ReportedUnit.RATIO.value
    elif expected_unit_type is UnitType.RATIO and unit is ReportedUnit.RATIO:
        scale = Decimal("1")
        normalized_unit = ReportedUnit.RATIO.value
    else:
        raise UnitNormalizationBlocked(
            f"incompatible reported unit {unit.value} for {expected_unit_type.value}"
        )
    return UnitNormalizationResult(
        original_value=value,
        original_unit=unit,
        normalized_value=value * scale,
        normalized_unit=normalized_unit,
        scale_factor=scale,
    )


def require_same_currency(currencies: tuple[str | None, ...]) -> str:
    """Return the common currency or block a mixed/unknown-currency calculation."""

    if not currencies or any(currency is None for currency in currencies):
        raise UnitNormalizationBlocked("currency is required for every monetary input")
    values = tuple(currency for currency in currencies if currency is not None)
    if any(
        len(currency) != 3 or not currency.isascii() or not currency.isupper()
        for currency in values
    ):
        raise UnitNormalizationBlocked("currency must be an uppercase ISO 4217 code")
    if len(set(values)) != 1:
        raise UnitNormalizationBlocked("currency mismatch blocks deterministic calculation")
    return values[0]
