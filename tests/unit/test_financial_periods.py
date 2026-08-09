from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from stock_research_agent.domain.financials.enums import FactNature
from stock_research_agent.domain.financials.periods import (
    FinancialPeriod,
    PeriodSemanticsError,
    PeriodType,
    assess_period_comparability,
)


def test_duration_period_uses_explicit_source_fiscal_identity_and_inclusive_days() -> None:
    period = FinancialPeriod.create(
        fiscal_year=2026,
        fiscal_quarter=2,
        fiscal_period="Q2",
        period_type=PeriodType.QUARTER,
        fact_nature=FactNature.DURATION,
        period_start=date(2025, 12, 1),
        period_end=date(2026, 2, 28),
        filing_date=date(2026, 4, 1),
        published_at=datetime(2026, 4, 1, 20, tzinfo=UTC),
        is_cumulative=False,
        is_single_quarter=True,
        accounting_standard="US_GAAP",
        source_form_type="10-Q",
    )

    assert period.fiscal_year == 2026
    assert period.period_end.year == 2026
    assert period.duration_days == 90
    assert period.is_annual is False
    assert period.is_ttm is False


def test_fiscal_year_cannot_be_derived_from_calendar_year() -> None:
    with pytest.raises(PeriodSemanticsError, match="fiscal_year"):
        FinancialPeriod.create(
            fiscal_year=None,
            fiscal_quarter=1,
            fiscal_period="Q1",
            period_type=PeriodType.QUARTER,
            fact_nature=FactNature.DURATION,
            period_start=date(2025, 9, 1),
            period_end=date(2025, 11, 30),
            filing_date=None,
            published_at=None,
            is_cumulative=False,
            is_single_quarter=True,
            accounting_standard="US_GAAP",
            source_form_type="10-Q",
        )


def test_instant_period_has_no_duration_or_cumulative_flags() -> None:
    period = FinancialPeriod.create(
        fiscal_year=2025,
        fiscal_quarter=4,
        fiscal_period="FY",
        period_type=PeriodType.INSTANT,
        fact_nature=FactNature.INSTANT,
        period_start=None,
        period_end=date(2025, 12, 31),
        filing_date=date(2026, 3, 1),
        published_at=None,
        is_cumulative=False,
        is_single_quarter=False,
        accounting_standard="CAS",
        source_form_type="ANNUAL_REPORT",
    )

    assert period.duration_days is None
    assert period.is_annual is False
    with pytest.raises(PeriodSemanticsError, match="instant"):
        FinancialPeriod.create(
            fiscal_year=2025,
            fiscal_quarter=4,
            fiscal_period="FY",
            period_type=PeriodType.INSTANT,
            fact_nature=FactNature.INSTANT,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            filing_date=None,
            published_at=None,
            is_cumulative=True,
            is_single_quarter=False,
            accounting_standard="CAS",
            source_form_type="ANNUAL_REPORT",
        )


def test_duration_and_instant_nature_cannot_be_mixed() -> None:
    with pytest.raises(PeriodSemanticsError, match="duration period"):
        FinancialPeriod.create(
            fiscal_year=2025,
            fiscal_quarter=4,
            fiscal_period="FY",
            period_type=PeriodType.ANNUAL,
            fact_nature=FactNature.INSTANT,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            filing_date=None,
            published_at=None,
            is_cumulative=False,
            is_single_quarter=False,
            accounting_standard="CAS",
            source_form_type="ANNUAL_REPORT",
        )


def test_period_dates_are_not_substituted_for_publication_time() -> None:
    period = FinancialPeriod.create(
        fiscal_year=2025,
        fiscal_quarter=None,
        fiscal_period="FY",
        period_type=PeriodType.ANNUAL,
        fact_nature=FactNature.DURATION,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        filing_date=date(2026, 3, 31),
        published_at=None,
        is_cumulative=True,
        is_single_quarter=False,
        accounting_standard="CAS",
        source_form_type="ANNUAL_REPORT",
    )

    assert period.published_at is None
    assert period.filing_date != period.period_end


def test_53_week_year_preserves_actual_duration_and_warning() -> None:
    current = FinancialPeriod.create(
        fiscal_year=2026,
        fiscal_quarter=None,
        fiscal_period="FY",
        period_type=PeriodType.ANNUAL,
        fact_nature=FactNature.DURATION,
        period_start=date(2025, 9, 1),
        period_end=date(2026, 9, 6),
        filing_date=None,
        published_at=None,
        is_cumulative=True,
        is_single_quarter=False,
        accounting_standard="US_GAAP",
        source_form_type="10-K",
    )
    prior = FinancialPeriod.create(
        fiscal_year=2025,
        fiscal_quarter=None,
        fiscal_period="FY",
        period_type=PeriodType.ANNUAL,
        fact_nature=FactNature.DURATION,
        period_start=date(2024, 9, 1),
        period_end=date(2025, 8, 31),
        filing_date=None,
        published_at=None,
        is_cumulative=True,
        is_single_quarter=False,
        accounting_standard="US_GAAP",
        source_form_type="10-K",
    )

    result = assess_period_comparability(current, prior)

    assert current.duration_days == 371
    assert result.comparable is True
    assert result.warnings == ("PERIOD_LENGTH_DIFFERS_BY_6_DAYS", "FIFTY_THREE_WEEK_PERIOD")


def test_materially_different_duration_is_not_comparable() -> None:
    quarter = FinancialPeriod.create(
        fiscal_year=2026,
        fiscal_quarter=1,
        fiscal_period="Q1",
        period_type=PeriodType.QUARTER,
        fact_nature=FactNature.DURATION,
        period_start=date(2025, 9, 1),
        period_end=date(2025, 11, 30),
        filing_date=None,
        published_at=None,
        is_cumulative=False,
        is_single_quarter=True,
        accounting_standard="US_GAAP",
        source_form_type="10-Q",
    )
    half_year = FinancialPeriod.create(
        fiscal_year=2025,
        fiscal_quarter=2,
        fiscal_period="H1",
        period_type=PeriodType.HALF_YEAR,
        fact_nature=FactNature.DURATION,
        period_start=date(2024, 9, 1),
        period_end=date(2025, 2, 28),
        filing_date=None,
        published_at=None,
        is_cumulative=True,
        is_single_quarter=False,
        accounting_standard="US_GAAP",
        source_form_type="10-Q",
    )

    result = assess_period_comparability(quarter, half_year)

    assert result.comparable is False
    assert "PERIOD_LENGTH_NOT_COMPARABLE" in result.warnings
