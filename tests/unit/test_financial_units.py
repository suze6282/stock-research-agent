from __future__ import annotations

from decimal import Decimal

import pytest

from stock_research_agent.domain.financials.enums import UnitType
from stock_research_agent.domain.financials.units import (
    ReportedUnit,
    UnitNormalizationBlocked,
    normalize_unit,
    require_same_currency,
)


@pytest.mark.parametrize(
    ("reported_unit", "value", "expected_value", "expected_scale"),
    [
        (ReportedUnit.ONE, Decimal("12.345678901234"), Decimal("12.345678901234"), Decimal("1")),
        (ReportedUnit.THOUSAND, Decimal("1.25"), Decimal("1250.00"), Decimal("1000")),
        (ReportedUnit.MILLION, Decimal("1.25"), Decimal("1250000.00"), Decimal("1000000")),
        (
            ReportedUnit.BILLION,
            Decimal("1.25"),
            Decimal("1250000000.00"),
            Decimal("1000000000"),
        ),
    ],
)
def test_monetary_scale_is_exact_and_reproducible(
    reported_unit: ReportedUnit,
    value: Decimal,
    expected_value: Decimal,
    expected_scale: Decimal,
) -> None:
    result = normalize_unit(value, reported_unit, UnitType.MONETARY_AMOUNT)

    assert result.normalized_value == expected_value
    assert result.scale_factor == expected_scale
    assert result.original_value == value
    assert result.original_unit is reported_unit
    assert result.normalized_unit == "ONE"


def test_percent_and_ratio_are_not_confused() -> None:
    percent = normalize_unit(Decimal("15"), ReportedUnit.PERCENT, UnitType.RATIO)
    ratio = normalize_unit(Decimal("0.15"), ReportedUnit.RATIO, UnitType.RATIO)

    assert percent.normalized_value == Decimal("0.15")
    assert percent.scale_factor == Decimal("0.01")
    assert ratio.normalized_value == Decimal("0.15")
    assert ratio.scale_factor == Decimal("1")


def test_shares_and_per_share_are_not_monetary_amounts() -> None:
    shares = normalize_unit(Decimal("100"), ReportedUnit.SHARES, UnitType.SHARES)
    per_share = normalize_unit(Decimal("1.23"), ReportedUnit.PER_SHARE, UnitType.PER_SHARE)

    assert shares.normalized_unit == "SHARES"
    assert per_share.normalized_unit == "PER_SHARE"
    with pytest.raises(UnitNormalizationBlocked, match="incompatible"):
        normalize_unit(Decimal("100"), ReportedUnit.SHARES, UnitType.MONETARY_AMOUNT)
    with pytest.raises(UnitNormalizationBlocked, match="incompatible"):
        normalize_unit(Decimal("1.23"), ReportedUnit.PER_SHARE, UnitType.MONETARY_AMOUNT)


@pytest.mark.parametrize("value", [1.25, float("nan"), float("inf")])
def test_binary_float_is_rejected(value: float) -> None:
    with pytest.raises(TypeError, match="Decimal"):
        normalize_unit(value, ReportedUnit.ONE, UnitType.MONETARY_AMOUNT)  # type: ignore[arg-type]


def test_unknown_unit_is_blocked_not_guessed() -> None:
    with pytest.raises(UnitNormalizationBlocked, match="unknown unit"):
        normalize_unit(Decimal("12"), "万元", UnitType.MONETARY_AMOUNT)  # type: ignore[arg-type]


def test_cross_currency_calculation_is_blocked() -> None:
    assert require_same_currency(("USD", "USD")) == "USD"
    with pytest.raises(UnitNormalizationBlocked, match="currency mismatch"):
        require_same_currency(("USD", "CNY"))
    with pytest.raises(UnitNormalizationBlocked, match="currency is required"):
        require_same_currency(("USD", None))


def test_unit_normalization_does_not_round_internal_precision() -> None:
    value = Decimal("0.1234567890123456789012345678")

    result = normalize_unit(value, ReportedUnit.ONE, UnitType.MONETARY_AMOUNT)

    assert result.normalized_value == value
