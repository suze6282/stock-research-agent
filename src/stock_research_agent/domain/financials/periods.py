"""Explicit fiscal-period semantics and comparability checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from stock_research_agent.domain.financials.enums import FactNature


class PeriodType(StrEnum):
    ANNUAL = "ANNUAL"
    QUARTER = "QUARTER"
    HALF_YEAR = "HALF_YEAR"
    NINE_MONTH_YTD = "NINE_MONTH_YTD"
    YEAR_TO_DATE = "YEAR_TO_DATE"
    TTM = "TTM"
    INSTANT = "INSTANT"


class PeriodSemanticsError(ValueError):
    """A period cannot be represented without inventing fiscal semantics."""


@dataclass(frozen=True)
class FinancialPeriod:
    fiscal_year: int
    fiscal_quarter: int | None
    fiscal_period: str
    period_type: PeriodType
    fact_nature: FactNature
    period_start: date | None
    period_end: date
    filing_date: date | None
    published_at: datetime | None
    duration_days: int | None
    is_annual: bool
    is_cumulative: bool
    is_single_quarter: bool
    is_ttm: bool
    accounting_standard: str
    source_form_type: str

    @classmethod
    def create(
        cls,
        *,
        fiscal_year: int | None,
        fiscal_quarter: int | None,
        fiscal_period: str,
        period_type: PeriodType,
        fact_nature: FactNature,
        period_start: date | None,
        period_end: date,
        filing_date: date | None,
        published_at: datetime | None,
        is_cumulative: bool,
        is_single_quarter: bool,
        accounting_standard: str,
        source_form_type: str,
    ) -> FinancialPeriod:
        if fiscal_year is None:
            raise PeriodSemanticsError("fiscal_year must come from source fiscal identity")
        if not 1900 <= fiscal_year <= 9999:
            raise PeriodSemanticsError("fiscal_year is outside the supported range")
        if fiscal_quarter is not None and fiscal_quarter not in {1, 2, 3, 4}:
            raise PeriodSemanticsError("fiscal_quarter must be between 1 and 4")
        if not fiscal_period or not accounting_standard or not source_form_type:
            raise PeriodSemanticsError("period source vocabulary must not be empty")
        if published_at is not None:
            if published_at.tzinfo is None or published_at.utcoffset() is None:
                raise PeriodSemanticsError("published_at must be timezone aware")
            published_at = published_at.astimezone(UTC)

        if period_type is PeriodType.INSTANT:
            if fact_nature is not FactNature.INSTANT:
                raise PeriodSemanticsError("instant period requires instant fact nature")
            if period_start is not None or is_cumulative or is_single_quarter:
                raise PeriodSemanticsError(
                    "instant periods cannot have a start, duration, cumulative or quarter flag"
                )
            duration_days = None
        else:
            if fact_nature is FactNature.INSTANT:
                raise PeriodSemanticsError("duration period cannot contain an instant fact")
            if period_start is None:
                raise PeriodSemanticsError("duration period requires period_start")
            if period_end < period_start:
                raise PeriodSemanticsError("period_end cannot precede period_start")
            duration_days = (period_end - period_start).days + 1

        return cls(
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter,
            fiscal_period=fiscal_period,
            period_type=period_type,
            fact_nature=fact_nature,
            period_start=period_start,
            period_end=period_end,
            filing_date=filing_date,
            published_at=published_at,
            duration_days=duration_days,
            is_annual=period_type is PeriodType.ANNUAL,
            is_cumulative=is_cumulative,
            is_single_quarter=is_single_quarter,
            is_ttm=period_type is PeriodType.TTM,
            accounting_standard=accounting_standard,
            source_form_type=source_form_type,
        )


@dataclass(frozen=True)
class PeriodComparability:
    comparable: bool
    warnings: tuple[str, ...]


def assess_period_comparability(
    current: FinancialPeriod,
    comparison: FinancialPeriod,
    *,
    maximum_duration_difference_days: int = 7,
) -> PeriodComparability:
    """Compare source periods without normalizing real 52/53-week durations."""

    warnings: list[str] = []
    comparable = True
    if current.fact_nature is not comparison.fact_nature:
        warnings.append("FACT_NATURE_MISMATCH")
        comparable = False
    if current.period_type is not comparison.period_type:
        warnings.append("PERIOD_TYPE_MISMATCH")
        comparable = False
    if current.accounting_standard != comparison.accounting_standard:
        warnings.append("ACCOUNTING_STANDARD_MISMATCH")
        comparable = False
    if current.duration_days is None or comparison.duration_days is None:
        if current.duration_days != comparison.duration_days:
            warnings.append("DURATION_SHAPE_MISMATCH")
            comparable = False
    else:
        difference = abs(current.duration_days - comparison.duration_days)
        if difference:
            if difference > maximum_duration_difference_days:
                warnings.append("PERIOD_LENGTH_NOT_COMPARABLE")
                comparable = False
            else:
                warnings.append(f"PERIOD_LENGTH_DIFFERS_BY_{difference}_DAYS")
        if current.duration_days >= 370 or comparison.duration_days >= 370:
            warnings.append("FIFTY_THREE_WEEK_PERIOD")
    return PeriodComparability(comparable=comparable, warnings=tuple(warnings))
