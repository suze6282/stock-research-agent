"""Deterministic period derivations used before metric formulas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from stock_research_agent.domain.financials.concepts import CanonicalConcept, get_concept
from stock_research_agent.domain.financials.periods import (
    FinancialPeriod,
    PeriodType,
    assess_period_comparability,
)


class CalculationBlocked(ValueError):
    """Required deterministic calculation semantics or inputs are unavailable."""


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CalculationBlocked(f"{field_name} must be timezone aware")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class FinancialValue:
    fact_id: UUID
    security_id: UUID
    concept: CanonicalConcept
    period: FinancialPeriod
    value: Decimal
    normalized_unit: str
    currency_code: str | None
    accounting_basis: str
    source_published_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("financial value must be a finite Decimal")
        if not self.normalized_unit or not self.accounting_basis:
            raise ValueError("normalized unit and accounting basis are required")
        if self.source_published_at is not None:
            object.__setattr__(
                self,
                "source_published_at",
                _aware_utc(self.source_published_at, field_name="source_published_at"),
            )


@dataclass(frozen=True)
class DerivedFinancialValue:
    concept: CanonicalConcept
    value: Decimal
    normalized_unit: str
    currency_code: str | None
    input_fact_ids: tuple[UUID, ...]
    formula_version: str
    method: str
    warnings: tuple[str, ...]
    is_derived_from_cumulative: bool


def _require_visible(value: FinancialValue, cutoff: datetime) -> None:
    if value.source_published_at is None:
        raise CalculationBlocked("source_published_at is required for as-of calculation")
    if value.source_published_at > cutoff:
        raise CalculationBlocked("fact was not public at the research as-of time")


def _require_compatible(values: tuple[FinancialValue, ...]) -> None:
    first = values[0]
    for value in values[1:]:
        if value.security_id != first.security_id:
            raise CalculationBlocked("security mismatch blocks deterministic calculation")
        if value.concept is not first.concept:
            raise CalculationBlocked("concept mismatch blocks deterministic calculation")
        if value.currency_code != first.currency_code:
            raise CalculationBlocked("currency mismatch blocks deterministic calculation")
        if value.normalized_unit != first.normalized_unit:
            raise CalculationBlocked("unit mismatch blocks deterministic calculation")
        if value.accounting_basis != first.accounting_basis:
            raise CalculationBlocked("accounting basis mismatch blocks deterministic calculation")


def _cumulative_stage(period: FinancialPeriod) -> int:
    if period.period_type is PeriodType.QUARTER and period.fiscal_quarter == 1:
        return 1
    if period.period_type is PeriodType.HALF_YEAR and period.fiscal_quarter == 2:
        return 2
    if period.period_type is PeriodType.NINE_MONTH_YTD and period.fiscal_quarter == 3:
        return 3
    if period.period_type is PeriodType.ANNUAL:
        return 4
    raise CalculationBlocked("unsupported cumulative fiscal-period sequence")


def deaccumulate_quarter(
    current_cumulative: FinancialValue,
    previous_cumulative: FinancialValue | None,
    *,
    research_as_of_time: datetime,
) -> DerivedFinancialValue:
    """Derive one A-share quarter from explicit cumulative reported facts."""

    cutoff = _aware_utc(research_as_of_time, field_name="research_as_of_time")
    concept = get_concept(current_cumulative.concept)
    if not concept.supports_cumulative or concept.fact_nature.value != "DURATION":
        raise CalculationBlocked(f"{concept.code.value} cannot be de-accumulated")
    if not current_cumulative.period.is_cumulative:
        raise CalculationBlocked("current fact must be explicitly cumulative")
    _require_visible(current_cumulative, cutoff)
    stage = _cumulative_stage(current_cumulative.period)
    input_ids: tuple[UUID, ...]

    if stage == 1:
        if previous_cumulative is not None:
            raise CalculationBlocked("Q1 cumulative derivation must not have a predecessor")
        value = current_cumulative.value
        input_ids = (current_cumulative.fact_id,)
    else:
        if previous_cumulative is None:
            raise CalculationBlocked("previous cumulative fact is required")
        _require_compatible((current_cumulative, previous_cumulative))
        _require_visible(previous_cumulative, cutoff)
        if not previous_cumulative.period.is_cumulative:
            raise CalculationBlocked("previous fact must be explicitly cumulative")
        if current_cumulative.period.fiscal_year != previous_cumulative.period.fiscal_year:
            raise CalculationBlocked("cumulative facts must belong to the same fiscal year")
        if _cumulative_stage(previous_cumulative.period) != stage - 1:
            raise CalculationBlocked("cumulative periods must be consecutive")
        if (
            current_cumulative.period.period_start != previous_cumulative.period.period_start
            or current_cumulative.period.period_end <= previous_cumulative.period.period_end
        ):
            raise CalculationBlocked("cumulative periods must share a continuous source start")
        value = current_cumulative.value - previous_cumulative.value
        input_ids = (previous_cumulative.fact_id, current_cumulative.fact_id)

    warnings = ("NEGATIVE_DEACCUMULATED_VALUE",) if value < 0 else ()
    return DerivedFinancialValue(
        concept=current_cumulative.concept,
        value=value,
        normalized_unit=current_cumulative.normalized_unit,
        currency_code=current_cumulative.currency_code,
        input_fact_ids=input_ids,
        formula_version="deaccumulation-v1.0.0",
        method="CUMULATIVE_DIFFERENCE",
        warnings=warnings,
        is_derived_from_cumulative=True,
    )


def _quarter_index(period: FinancialPeriod) -> int:
    if period.fiscal_quarter is None:
        raise CalculationBlocked("single-quarter fact requires an explicit fiscal quarter")
    return period.fiscal_year * 4 + period.fiscal_quarter - 1


def calculate_ttm_four_quarters(
    quarters: tuple[FinancialValue, ...],
    *,
    research_as_of_time: datetime,
) -> DerivedFinancialValue:
    """Sum exactly four comparable, consecutive single-quarter facts."""

    if len(quarters) != 4:
        raise CalculationBlocked("TTM method A requires exactly four quarters")
    cutoff = _aware_utc(research_as_of_time, field_name="research_as_of_time")
    ordered = tuple(sorted(quarters, key=lambda fact: fact.period.period_end))
    _require_compatible(ordered)
    concept = get_concept(ordered[0].concept)
    if not concept.supports_ttm or not concept.supports_duration:
        raise CalculationBlocked(f"{concept.code.value} is not eligible for TTM")
    if any(fact.period.is_cumulative or not fact.period.is_single_quarter for fact in ordered):
        raise CalculationBlocked("TTM method A requires non-cumulative single quarters")
    for fact in ordered:
        _require_visible(fact, cutoff)
    indexes = tuple(_quarter_index(fact.period) for fact in ordered)
    if any(later != earlier + 1 for earlier, later in zip(indexes[:-1], indexes[1:], strict=True)):
        raise CalculationBlocked("TTM quarters must be consecutive")

    duration_days = sum(fact.period.duration_days or 0 for fact in ordered)
    warnings = ("FIFTY_THREE_WEEK_PERIOD",) if duration_days >= 370 else ()
    return DerivedFinancialValue(
        concept=ordered[0].concept,
        value=sum((fact.value for fact in ordered), start=Decimal("0")),
        normalized_unit=ordered[0].normalized_unit,
        currency_code=ordered[0].currency_code,
        input_fact_ids=tuple(fact.fact_id for fact in ordered),
        formula_version="ttm-four-quarters-v1.0.0",
        method="FOUR_QUARTERS",
        warnings=warnings,
        is_derived_from_cumulative=False,
    )


def calculate_ttm_bridge(
    annual: FinancialValue,
    latest_ytd: FinancialValue,
    prior_year_ytd: FinancialValue,
    *,
    research_as_of_time: datetime,
) -> DerivedFinancialValue:
    """Calculate FY + latest YTD - prior comparable YTD with explicit lineage."""

    cutoff = _aware_utc(research_as_of_time, field_name="research_as_of_time")
    inputs = (annual, latest_ytd, prior_year_ytd)
    _require_compatible(inputs)
    concept = get_concept(annual.concept)
    if not concept.supports_ttm or not concept.supports_duration:
        raise CalculationBlocked(f"{concept.code.value} is not eligible for TTM")
    for fact in inputs:
        _require_visible(fact, cutoff)
    if annual.period.period_type is not PeriodType.ANNUAL or not annual.period.is_cumulative:
        raise CalculationBlocked("TTM bridge requires one cumulative annual fact")
    if not latest_ytd.period.is_cumulative or not prior_year_ytd.period.is_cumulative:
        raise CalculationBlocked("TTM bridge requires cumulative YTD facts")
    if latest_ytd.period.fiscal_year != annual.period.fiscal_year + 1:
        raise CalculationBlocked("latest YTD must follow the annual fiscal year")
    if prior_year_ytd.period.fiscal_year != annual.period.fiscal_year:
        raise CalculationBlocked("prior YTD must belong to the annual fiscal year")
    if latest_ytd.period.fiscal_quarter != prior_year_ytd.period.fiscal_quarter:
        raise CalculationBlocked("YTD fiscal quarters must match")
    comparability = assess_period_comparability(latest_ytd.period, prior_year_ytd.period)
    if not comparability.comparable:
        raise CalculationBlocked("YTD periods are not comparable")

    return DerivedFinancialValue(
        concept=annual.concept,
        value=annual.value + latest_ytd.value - prior_year_ytd.value,
        normalized_unit=annual.normalized_unit,
        currency_code=annual.currency_code,
        input_fact_ids=tuple(fact.fact_id for fact in inputs),
        formula_version="ttm-annual-ytd-bridge-v1.0.0",
        method="ANNUAL_YTD_BRIDGE",
        warnings=comparability.warnings,
        is_derived_from_cumulative=False,
    )
