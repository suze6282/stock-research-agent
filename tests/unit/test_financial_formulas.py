from __future__ import annotations

from decimal import Decimal

import pytest

from stock_research_agent.domain.financials.enums import QualityStatus
from stock_research_agent.domain.financials.formulas import (
    FORMULA_REGISTRY,
    FormulaInput,
    MetricCode,
    MetricValueState,
    execute_formula,
    get_formula,
)


def _amount(value: str | None, *, currency: str = "USD", unit: str = "ONE") -> FormulaInput:
    return FormulaInput(
        value=None if value is None else Decimal(value),
        unit=unit,
        currency_code=currency,
    )


def _ratio(value: str | None) -> FormulaInput:
    return FormulaInput(
        value=None if value is None else Decimal(value),
        unit="RATIO",
        currency_code=None,
    )


def _shares(value: str | None) -> FormulaInput:
    return FormulaInput(
        value=None if value is None else Decimal(value),
        unit="SHARES",
        currency_code=None,
    )


def _price(value: str | None, *, currency: str = "USD") -> FormulaInput:
    return FormulaInput(
        value=None if value is None else Decimal(value),
        unit="PER_SHARE",
        currency_code=currency,
    )


REQUIRED_METRICS = {
    "revenue_growth",
    "gross_margin",
    "operating_margin",
    "net_margin_parent",
    "roe_parent",
    "roa_total",
    "roic",
    "operating_cash_flow",
    "free_cash_flow",
    "liabilities_to_assets",
    "net_debt",
    "basic_eps",
    "diluted_eps",
    "market_cap",
    "pe_ttm_diluted",
    "pb_parent",
    "ps_ttm",
    "enterprise_value",
    "ev_to_ebitda_ttm",
    "fcf_yield_ttm",
    "revenue_ttm",
    "net_income_parent_ttm",
    "ebitda_ttm",
}


def test_formula_registry_is_complete_versioned_and_not_executable_text() -> None:
    assert {definition.metric_code.value for definition in FORMULA_REGISTRY} == REQUIRED_METRICS
    assert len(FORMULA_REGISTRY) == len(REQUIRED_METRICS)
    assert all(definition.formula_version == "1.0.0" for definition in FORMULA_REGISTRY)
    assert all(
        "eval" not in definition.formula_expression.casefold() for definition in FORMULA_REGISTRY
    )
    assert get_formula(MetricCode.NET_DEBT).formula_expression == "total_debt - cash"
    with pytest.raises(KeyError):
        get_formula("user_supplied_python")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("metric", "inputs", "expected"),
    [
        (
            MetricCode.REVENUE_GROWTH,
            {"current_revenue": _amount("125"), "prior_revenue": _amount("100")},
            Decimal("0.25"),
        ),
        (
            MetricCode.GROSS_MARGIN,
            {"revenue": _amount("100"), "cost_of_revenue": _amount("60")},
            Decimal("0.4"),
        ),
        (
            MetricCode.OPERATING_MARGIN,
            {"operating_income": _amount("15"), "revenue": _amount("100")},
            Decimal("0.15"),
        ),
        (
            MetricCode.NET_MARGIN_PARENT,
            {"net_income_parent": _amount("12"), "revenue": _amount("100")},
            Decimal("0.12"),
        ),
    ],
)
def test_growth_and_margin_golden_values(
    metric: MetricCode,
    inputs: dict[str, FormulaInput],
    expected: Decimal,
) -> None:
    result = execute_formula(metric, inputs)

    assert result.value == expected
    assert result.value_state is MetricValueState.VALUE
    assert result.quality_status is QualityStatus.PASS


def test_negative_margin_is_numeric_with_warning_and_zero_revenue_is_nm() -> None:
    negative = execute_formula(
        MetricCode.GROSS_MARGIN,
        {"revenue": _amount("100"), "cost_of_revenue": _amount("120")},
    )
    zero_denominator = execute_formula(
        MetricCode.GROSS_MARGIN,
        {"revenue": _amount("0"), "cost_of_revenue": _amount("0")},
    )

    assert negative.value == Decimal("-0.2")
    assert negative.quality_status is QualityStatus.PARTIAL
    assert negative.warnings == ("NEGATIVE_GROSS_MARGIN",)
    assert zero_denominator.value is None
    assert zero_denominator.value_state is MetricValueState.NOT_MEANINGFUL
    assert zero_denominator.warnings == ("DENOMINATOR_NON_POSITIVE",)


def test_missing_is_null_and_never_zero() -> None:
    result = execute_formula(
        MetricCode.GROSS_MARGIN,
        {"revenue": _amount("100"), "cost_of_revenue": _amount(None)},
    )

    assert result.value is None
    assert result.value_state is MetricValueState.NULL
    assert result.quality_status is QualityStatus.BLOCKED
    assert result.warnings == ("SOURCE_MISSING:cost_of_revenue",)


@pytest.mark.parametrize(
    ("metric", "expected_unit"),
    [
        (MetricCode.OPERATING_CASH_FLOW, "ONE"),
        (MetricCode.REVENUE_TTM, "ONE"),
        (MetricCode.BASIC_EPS, "PER_SHARE"),
        (MetricCode.GROSS_MARGIN, "RATIO"),
    ],
)
def test_blocked_metric_preserves_declared_output_unit(
    metric: MetricCode,
    expected_unit: str,
) -> None:
    result = execute_formula(metric, {})

    assert result.value is None
    assert result.unit == expected_unit


def test_roe_and_roa_use_opening_and_closing_average_balances() -> None:
    roe = execute_formula(
        MetricCode.ROE_PARENT,
        {
            "net_income_parent": _amount("20"),
            "opening_equity_parent": _amount("80"),
            "closing_equity_parent": _amount("120"),
        },
    )
    roa = execute_formula(
        MetricCode.ROA_TOTAL,
        {
            "net_income_total": _amount("15"),
            "opening_total_assets": _amount("200"),
            "closing_total_assets": _amount("300"),
        },
    )

    assert roe.value == Decimal("0.2")
    assert roa.value == Decimal("0.06")
    missing_opening = execute_formula(
        MetricCode.ROE_PARENT,
        {
            "net_income_parent": _amount("20"),
            "opening_equity_parent": _amount(None),
            "closing_equity_parent": _amount("120"),
        },
    )
    assert missing_opening.value_state is MetricValueState.NULL


def test_nonpositive_average_equity_is_not_meaningful() -> None:
    result = execute_formula(
        MetricCode.ROE_PARENT,
        {
            "net_income_parent": _amount("-10"),
            "opening_equity_parent": _amount("-20"),
            "closing_equity_parent": _amount("0"),
        },
    )

    assert result.value is None
    assert result.value_state is MetricValueState.NOT_MEANINGFUL


def test_roic_uses_nopat_and_average_invested_capital() -> None:
    result = execute_formula(
        MetricCode.ROIC,
        {
            "operating_income": _amount("20"),
            "pretax_income": _amount("25"),
            "income_tax_expense": _amount("5"),
            "opening_total_equity": _amount("100"),
            "closing_total_equity": _amount("120"),
            "opening_total_debt": _amount("50"),
            "closing_total_debt": _amount("60"),
            "opening_cash": _amount("20"),
            "closing_cash": _amount("30"),
        },
    )

    assert result.value == Decimal("4") / Decimal("35")


@pytest.mark.parametrize(("pretax", "tax"), [("0", "0"), ("10", "12"), ("10", "-1")])
def test_roic_blocks_unusable_effective_tax_rate(pretax: str, tax: str) -> None:
    result = execute_formula(
        MetricCode.ROIC,
        {
            "operating_income": _amount("20"),
            "pretax_income": _amount(pretax),
            "income_tax_expense": _amount(tax),
            "opening_total_equity": _amount("100"),
            "closing_total_equity": _amount("120"),
            "opening_total_debt": _amount("50"),
            "closing_total_debt": _amount("60"),
            "opening_cash": _amount("20"),
            "closing_cash": _amount("30"),
        },
    )

    assert result.quality_status is QualityStatus.BLOCKED
    assert result.value is None
    assert "EFFECTIVE_TAX_RATE_UNUSABLE" in result.warnings


def test_cash_flow_debt_and_net_debt_golden_values() -> None:
    ocf = execute_formula(MetricCode.OPERATING_CASH_FLOW, {"reported_ocf": _amount("25")})
    fcf = execute_formula(
        MetricCode.FREE_CASH_FLOW,
        {"operating_cash_flow": _amount("25"), "capital_expenditures": _amount("30")},
    )
    debt_ratio = execute_formula(
        MetricCode.LIABILITIES_TO_ASSETS,
        {"total_liabilities": _amount("60"), "total_assets": _amount("100")},
    )
    net_debt = execute_formula(
        MetricCode.NET_DEBT,
        {"total_debt": _amount("50"), "cash": _amount("80")},
    )

    assert ocf.value == Decimal("25")
    assert fcf.value == Decimal("-5")
    assert debt_ratio.value == Decimal("0.6")
    assert net_debt.value == Decimal("-30")
    assert "short_term_investments" not in get_formula(MetricCode.NET_DEBT).required_inputs


@pytest.mark.parametrize(
    "metric",
    [MetricCode.REVENUE_TTM, MetricCode.NET_INCOME_PARENT_TTM, MetricCode.EBITDA_TTM],
)
def test_ttm_formula_registry_sums_four_prevalidated_quarters(metric: MetricCode) -> None:
    inputs = {
        "quarter_1": _amount("1"),
        "quarter_2": _amount("2"),
        "quarter_3": _amount("3"),
        "quarter_4": _amount("4"),
    }

    result = execute_formula(metric, inputs)

    assert result.value == Decimal("10")
    assert result.consumed_inputs == ("quarter_1", "quarter_2", "quarter_3", "quarter_4")


def test_market_cap_uses_actual_period_end_shares() -> None:
    result = execute_formula(
        MetricCode.MARKET_CAP,
        {"price": _price("10.25"), "actual_shares_outstanding": _shares("1000")},
    )

    assert result.value == Decimal("10250.00")
    assert result.currency_code == "USD"
    assert result.unit == "ONE"


def test_pe_pb_ps_and_ev_valuation_golden_values() -> None:
    pe = execute_formula(
        MetricCode.PE_TTM_DILUTED,
        {"market_cap": _amount("1000"), "net_income_parent_ttm": _amount("100")},
    )
    pb = execute_formula(
        MetricCode.PB_PARENT,
        {"market_cap": _amount("1000"), "equity_parent": _amount("500")},
    )
    ps = execute_formula(
        MetricCode.PS_TTM,
        {"market_cap": _amount("1000"), "revenue_ttm": _amount("400")},
    )
    ev = execute_formula(
        MetricCode.ENTERPRISE_VALUE,
        {
            "market_cap": _amount("1000"),
            "total_debt": _amount("200"),
            "preferred_equity": _amount("10"),
            "minority_interest": _amount("20"),
            "cash": _amount("100"),
        },
    )

    assert pe.value == Decimal("10")
    assert pb.value == Decimal("2")
    assert ps.value == Decimal("2.5")
    assert ev.value == Decimal("1130")


def test_loss_pe_and_nonpositive_ebitda_are_nm_not_negative_multiple() -> None:
    pe = execute_formula(
        MetricCode.PE_TTM_DILUTED,
        {"market_cap": _amount("1000"), "net_income_parent_ttm": _amount("-10")},
    )
    multiple = execute_formula(
        MetricCode.EV_TO_EBITDA_TTM,
        {"enterprise_value": _amount("1000"), "ebitda_ttm": _amount("0")},
    )

    assert pe.value is None and pe.value_state is MetricValueState.NOT_MEANINGFUL
    assert multiple.value is None and multiple.value_state is MetricValueState.NOT_MEANINGFUL


def test_ev_requires_explicit_preferred_and_minority_values() -> None:
    result = execute_formula(
        MetricCode.ENTERPRISE_VALUE,
        {
            "market_cap": _amount("1000"),
            "total_debt": _amount("200"),
            "preferred_equity": _amount(None),
            "minority_interest": _amount("0"),
            "cash": _amount("100"),
        },
    )

    assert result.value is None
    assert result.warnings == ("SOURCE_MISSING:preferred_equity",)


def test_ev_to_ebitda_and_fcf_yield_preserve_signed_valid_values() -> None:
    multiple = execute_formula(
        MetricCode.EV_TO_EBITDA_TTM,
        {"enterprise_value": _amount("-50"), "ebitda_ttm": _amount("25")},
    )
    yield_result = execute_formula(
        MetricCode.FCF_YIELD_TTM,
        {"free_cash_flow_ttm": _amount("-10"), "market_cap": _amount("200")},
    )

    assert multiple.value == Decimal("-2")
    assert "NEGATIVE_ENTERPRISE_VALUE" in multiple.warnings
    assert yield_result.value == Decimal("-0.05")


def test_currency_and_unit_mismatch_block_arithmetic() -> None:
    currency = execute_formula(
        MetricCode.FREE_CASH_FLOW,
        {
            "operating_cash_flow": _amount("25", currency="USD"),
            "capital_expenditures": _amount("10", currency="CNY"),
        },
    )
    unit = execute_formula(
        MetricCode.GROSS_MARGIN,
        {
            "revenue": _amount("100", unit="ONE"),
            "cost_of_revenue": _amount("60", unit="MILLION"),
        },
    )

    assert currency.quality_status is QualityStatus.BLOCKED
    assert currency.warnings == ("INCOMPATIBLE_CURRENCY",)
    assert unit.quality_status is QualityStatus.BLOCKED
    assert unit.warnings == ("INCOMPATIBLE_UNIT",)


def test_zero_is_distinct_from_null_and_nm() -> None:
    result = execute_formula(
        MetricCode.FREE_CASH_FLOW,
        {"operating_cash_flow": _amount("10"), "capital_expenditures": _amount("10")},
    )

    assert result.value == Decimal("0")
    assert result.value_state is MetricValueState.ZERO
    assert result.quality_status is QualityStatus.PASS


def test_decimal_precision_is_not_rounded_inside_formula() -> None:
    result = execute_formula(
        MetricCode.OPERATING_MARGIN,
        {"operating_income": _amount("1"), "revenue": _amount("3")},
    )

    assert result.value == Decimal("1") / Decimal("3")


def test_binary_float_formula_input_is_rejected() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        FormulaInput(value=1.2, unit="ONE", currency_code="USD")  # type: ignore[arg-type]
