from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from stock_research_agent.domain.financials.calculations import (
    CalculationBlocked,
    FinancialValue,
    calculate_ttm_bridge,
    calculate_ttm_four_quarters,
    deaccumulate_quarter,
)
from stock_research_agent.domain.financials.concepts import CanonicalConcept
from stock_research_agent.domain.financials.enums import FactNature
from stock_research_agent.domain.financials.periods import FinancialPeriod, PeriodType

SECURITY_ID = UUID("40000000-0000-0000-0000-000000000001")
CUTOFF = datetime(2027, 4, 1, tzinfo=UTC)


def _period(
    fiscal_year: int,
    quarter: int | None,
    start: date,
    end: date,
    *,
    period_type: PeriodType = PeriodType.QUARTER,
    cumulative: bool = False,
    single_quarter: bool = True,
    accounting_standard: str = "CAS",
) -> FinancialPeriod:
    fiscal_period = "FY" if quarter is None else f"Q{quarter}"
    return FinancialPeriod.create(
        fiscal_year=fiscal_year,
        fiscal_quarter=quarter,
        fiscal_period=fiscal_period,
        period_type=period_type,
        fact_nature=FactNature.DURATION,
        period_start=start,
        period_end=end,
        filing_date=end,
        published_at=datetime(end.year, end.month, end.day, 8, tzinfo=UTC),
        is_cumulative=cumulative,
        is_single_quarter=single_quarter,
        accounting_standard=accounting_standard,
        source_form_type="ANNUAL_REPORT"
        if period_type is PeriodType.ANNUAL
        else "QUARTERLY_REPORT",
    )


def _fact(
    number: int,
    value: str,
    period: FinancialPeriod,
    *,
    concept: CanonicalConcept = CanonicalConcept.REVENUE,
    currency: str = "CNY",
    unit: str = "ONE",
    accounting_basis: str = "CAS_CONSOLIDATED",
    published_at: datetime | None = None,
) -> FinancialValue:
    return FinancialValue(
        fact_id=UUID(f"10000000-0000-0000-0000-{number:012d}"),
        security_id=SECURITY_ID,
        concept=concept,
        period=period,
        value=Decimal(value),
        normalized_unit=unit,
        currency_code=currency,
        accounting_basis=accounting_basis,
        source_published_at=published_at or period.published_at,
    )


def _a_share_ytd_facts() -> tuple[FinancialValue, ...]:
    start = date(2026, 1, 1)
    return (
        _fact(1, "10", _period(2026, 1, start, date(2026, 3, 31), cumulative=True)),
        _fact(
            2,
            "25",
            _period(
                2026,
                2,
                start,
                date(2026, 6, 30),
                period_type=PeriodType.HALF_YEAR,
                cumulative=True,
                single_quarter=False,
            ),
        ),
        _fact(
            3,
            "37",
            _period(
                2026,
                3,
                start,
                date(2026, 9, 30),
                period_type=PeriodType.NINE_MONTH_YTD,
                cumulative=True,
                single_quarter=False,
            ),
        ),
        _fact(
            4,
            "57",
            _period(
                2026,
                None,
                start,
                date(2026, 12, 31),
                period_type=PeriodType.ANNUAL,
                cumulative=True,
                single_quarter=False,
            ),
        ),
    )


def test_a_share_cumulative_values_are_split_into_exact_quarters() -> None:
    q1_ytd, h1_ytd, nine_month_ytd, annual = _a_share_ytd_facts()

    q1 = deaccumulate_quarter(q1_ytd, None, research_as_of_time=CUTOFF)
    q2 = deaccumulate_quarter(h1_ytd, q1_ytd, research_as_of_time=CUTOFF)
    q3 = deaccumulate_quarter(nine_month_ytd, h1_ytd, research_as_of_time=CUTOFF)
    q4 = deaccumulate_quarter(annual, nine_month_ytd, research_as_of_time=CUTOFF)

    assert (q1.value, q2.value, q3.value, q4.value) == tuple(
        Decimal(value) for value in ("10", "15", "12", "20")
    )
    assert q1.input_fact_ids == (q1_ytd.fact_id,)
    assert q4.input_fact_ids == (nine_month_ytd.fact_id, annual.fact_id)
    assert all(item.is_derived_from_cumulative for item in (q1, q2, q3, q4))
    assert all(item.formula_version == "deaccumulation-v1.0.0" for item in (q1, q2, q3, q4))


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("currency_code", "USD", "currency"),
        ("normalized_unit", "MILLION", "unit"),
        ("accounting_basis", "CAS_PARENT", "accounting basis"),
        ("security_id", UUID("40000000-0000-0000-0000-000000000002"), "security"),
        ("concept", CanonicalConcept.OPERATING_INCOME, "concept"),
    ],
)
def test_deaccumulation_blocks_incompatible_inputs(
    field: str,
    replacement: object,
    message: str,
) -> None:
    q1, h1, *_ = _a_share_ytd_facts()
    incompatible = FinancialValue(**{**q1.__dict__, field: replacement})

    with pytest.raises(CalculationBlocked, match=message):
        deaccumulate_quarter(h1, incompatible, research_as_of_time=CUTOFF)


@pytest.mark.parametrize(
    "concept",
    [
        CanonicalConcept.TOTAL_ASSETS,
        CanonicalConcept.BASIC_EPS,
        CanonicalConcept.BASIC_WEIGHTED_AVERAGE_SHARES,
    ],
)
def test_deaccumulation_blocks_instant_eps_and_weighted_shares(
    concept: CanonicalConcept,
) -> None:
    q1, h1, *_ = _a_share_ytd_facts()
    current = FinancialValue(**{**h1.__dict__, "concept": concept})
    prior = FinancialValue(**{**q1.__dict__, "concept": concept})

    with pytest.raises(CalculationBlocked):
        deaccumulate_quarter(current, prior, research_as_of_time=CUTOFF)


def test_negative_deaccumulation_is_retained_with_warning() -> None:
    q1, h1, *_ = _a_share_ytd_facts()
    lower_h1 = FinancialValue(**{**h1.__dict__, "value": Decimal("8")})

    result = deaccumulate_quarter(lower_h1, q1, research_as_of_time=CUTOFF)

    assert result.value == Decimal("-2")
    assert result.warnings == ("NEGATIVE_DEACCUMULATED_VALUE",)


def _four_quarters() -> tuple[FinancialValue, ...]:
    return (
        _fact(11, "10", _period(2025, 2, date(2025, 4, 1), date(2025, 6, 30))),
        _fact(12, "20", _period(2025, 3, date(2025, 7, 1), date(2025, 9, 30))),
        _fact(13, "30", _period(2025, 4, date(2025, 10, 1), date(2025, 12, 31))),
        _fact(14, "40", _period(2026, 1, date(2026, 1, 1), date(2026, 3, 31))),
    )


def test_ttm_method_a_sums_latest_four_comparable_quarters() -> None:
    quarters = tuple(reversed(_four_quarters()))

    result = calculate_ttm_four_quarters(quarters, research_as_of_time=CUTOFF)

    assert result.value == Decimal("100")
    assert result.method == "FOUR_QUARTERS"
    assert result.formula_version == "ttm-four-quarters-v1.0.0"
    assert result.input_fact_ids == tuple(fact.fact_id for fact in _four_quarters())
    assert calculate_ttm_four_quarters(quarters, research_as_of_time=CUTOFF) == result


def test_ttm_method_a_blocks_missing_or_nonconsecutive_quarter() -> None:
    quarters = _four_quarters()

    with pytest.raises(CalculationBlocked, match="four"):
        calculate_ttm_four_quarters(quarters[:3], research_as_of_time=CUTOFF)
    gap = FinancialValue(
        **{
            **quarters[-1].__dict__,
            "period": _period(2026, 2, date(2026, 4, 1), date(2026, 6, 30)),
        }
    )
    with pytest.raises(CalculationBlocked, match="consecutive"):
        calculate_ttm_four_quarters((*quarters[:3], gap), research_as_of_time=CUTOFF)


def test_ttm_method_b_uses_annual_ytd_bridge_with_lineage() -> None:
    annual = _fact(
        21,
        "100",
        _period(
            2025,
            None,
            date(2025, 1, 1),
            date(2025, 12, 31),
            period_type=PeriodType.ANNUAL,
            cumulative=True,
            single_quarter=False,
        ),
    )
    latest_ytd = _fact(
        22,
        "70",
        _period(
            2026,
            2,
            date(2026, 1, 1),
            date(2026, 6, 30),
            period_type=PeriodType.HALF_YEAR,
            cumulative=True,
            single_quarter=False,
        ),
    )
    prior_ytd = _fact(
        23,
        "60",
        _period(
            2025,
            2,
            date(2025, 1, 1),
            date(2025, 6, 30),
            period_type=PeriodType.HALF_YEAR,
            cumulative=True,
            single_quarter=False,
        ),
    )

    result = calculate_ttm_bridge(
        annual,
        latest_ytd,
        prior_ytd,
        research_as_of_time=CUTOFF,
    )

    assert result.value == Decimal("110")
    assert result.method == "ANNUAL_YTD_BRIDGE"
    assert result.formula_version == "ttm-annual-ytd-bridge-v1.0.0"
    assert result.input_fact_ids == (annual.fact_id, latest_ytd.fact_id, prior_ytd.fact_id)


def test_ttm_blocks_future_fact_and_instant_concept() -> None:
    quarters = _four_quarters()
    future = FinancialValue(
        **{
            **quarters[-1].__dict__,
            "source_published_at": datetime(2028, 1, 1, tzinfo=UTC),
        }
    )
    instant = tuple(
        FinancialValue(**{**fact.__dict__, "concept": CanonicalConcept.TOTAL_ASSETS})
        for fact in quarters
    )

    with pytest.raises(CalculationBlocked, match="as-of"):
        calculate_ttm_four_quarters((*quarters[:3], future), research_as_of_time=CUTOFF)
    with pytest.raises(CalculationBlocked, match="TTM"):
        calculate_ttm_four_quarters(instant, research_as_of_time=CUTOFF)
