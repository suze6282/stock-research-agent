"""Whitelist-only V0.1 metric formula registry and Decimal implementations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from stock_research_agent.domain.financials.enums import QualityStatus


class MetricCode(StrEnum):
    REVENUE_GROWTH = "revenue_growth"
    GROSS_MARGIN = "gross_margin"
    OPERATING_MARGIN = "operating_margin"
    NET_MARGIN_PARENT = "net_margin_parent"
    ROE_PARENT = "roe_parent"
    ROA_TOTAL = "roa_total"
    ROIC = "roic"
    OPERATING_CASH_FLOW = "operating_cash_flow"
    FREE_CASH_FLOW = "free_cash_flow"
    LIABILITIES_TO_ASSETS = "liabilities_to_assets"
    NET_DEBT = "net_debt"
    BASIC_EPS = "basic_eps"
    DILUTED_EPS = "diluted_eps"
    MARKET_CAP = "market_cap"
    PE_TTM_DILUTED = "pe_ttm_diluted"
    PB_PARENT = "pb_parent"
    PS_TTM = "ps_ttm"
    ENTERPRISE_VALUE = "enterprise_value"
    EV_TO_EBITDA_TTM = "ev_to_ebitda_ttm"
    FCF_YIELD_TTM = "fcf_yield_ttm"
    REVENUE_TTM = "revenue_ttm"
    NET_INCOME_PARENT_TTM = "net_income_parent_ttm"
    EBITDA_TTM = "ebitda_ttm"


class MetricValueState(StrEnum):
    VALUE = "VALUE"
    ZERO = "ZERO"
    NULL = "NULL"
    NOT_MEANINGFUL = "NOT_MEANINGFUL"


@dataclass(frozen=True)
class FormulaInput:
    value: Decimal | None
    unit: str
    currency_code: str | None

    def __post_init__(self) -> None:
        if self.value is not None:
            if not isinstance(self.value, Decimal):
                raise TypeError("formula values must be Decimal, never binary float")
            if not self.value.is_finite():
                raise ValueError("formula values must be finite")
        if not self.unit:
            raise ValueError("formula input unit must not be empty")
        if self.currency_code is not None and (
            len(self.currency_code) != 3
            or not self.currency_code.isascii()
            or not self.currency_code.isupper()
        ):
            raise ValueError("currency_code must be an uppercase ISO 4217 token")


@dataclass(frozen=True)
class FormulaDefinition:
    metric_code: MetricCode
    name: str
    formula_expression: str
    formula_version: str
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    period_requirement: str
    currency_requirement: str
    denominator_policy: str
    negative_value_policy: str
    status: str = "ACTIVE"


@dataclass(frozen=True)
class MetricResult:
    metric_code: MetricCode
    value: Decimal | None
    value_state: MetricValueState
    unit: str
    currency_code: str | None
    quality_status: QualityStatus
    formula_version: str
    warnings: tuple[str, ...]
    consumed_inputs: tuple[str, ...]


def _definition(
    code: MetricCode,
    expression: str,
    required: tuple[str, ...],
    *,
    period: str,
    currency: str = "SAME_CURRENCY",
    denominator: str = "NOT_APPLICABLE",
    negative: str = "ALLOWED",
    optional: tuple[str, ...] = (),
) -> FormulaDefinition:
    return FormulaDefinition(
        metric_code=code,
        name=code.value.replace("_", " ").title(),
        formula_expression=expression,
        formula_version="1.0.0",
        required_inputs=required,
        optional_inputs=optional,
        period_requirement=period,
        currency_requirement=currency,
        denominator_policy=denominator,
        negative_value_policy=negative,
    )


FORMULA_REGISTRY: tuple[FormulaDefinition, ...] = (
    _definition(
        MetricCode.REVENUE_GROWTH,
        "(current_revenue - prior_revenue) / prior_revenue",
        ("current_revenue", "prior_revenue"),
        period="COMPARABLE_DURATION",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.GROSS_MARGIN,
        "(revenue - cost_of_revenue) / revenue",
        ("revenue", "cost_of_revenue"),
        period="SAME_DURATION",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.OPERATING_MARGIN,
        "operating_income / revenue",
        ("operating_income", "revenue"),
        period="SAME_DURATION",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.NET_MARGIN_PARENT,
        "net_income_parent / revenue",
        ("net_income_parent", "revenue"),
        period="SAME_DURATION",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.ROE_PARENT,
        "net_income_parent / average(opening_equity_parent, closing_equity_parent)",
        ("net_income_parent", "opening_equity_parent", "closing_equity_parent"),
        period="DURATION_WITH_OPENING_AND_CLOSING",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.ROA_TOTAL,
        "net_income_total / average(opening_total_assets, closing_total_assets)",
        ("net_income_total", "opening_total_assets", "closing_total_assets"),
        period="DURATION_WITH_OPENING_AND_CLOSING",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.ROIC,
        "nopat / average(opening_invested_capital, closing_invested_capital)",
        (
            "operating_income",
            "pretax_income",
            "income_tax_expense",
            "opening_total_equity",
            "closing_total_equity",
            "opening_total_debt",
            "closing_total_debt",
            "opening_cash",
            "closing_cash",
        ),
        period="DURATION_WITH_OPENING_AND_CLOSING",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.OPERATING_CASH_FLOW,
        "reported_ocf",
        ("reported_ocf",),
        period="DURATION",
    ),
    _definition(
        MetricCode.FREE_CASH_FLOW,
        "operating_cash_flow - capital_expenditures",
        ("operating_cash_flow", "capital_expenditures"),
        period="SAME_DURATION",
    ),
    _definition(
        MetricCode.LIABILITIES_TO_ASSETS,
        "total_liabilities / total_assets",
        ("total_liabilities", "total_assets"),
        period="SAME_INSTANT",
        denominator="NON_POSITIVE_IS_NM",
        negative="NEGATIVE_LIABILITIES_BLOCKED",
    ),
    _definition(
        MetricCode.NET_DEBT,
        "total_debt - cash",
        ("total_debt", "cash"),
        period="SAME_INSTANT",
    ),
    _definition(
        MetricCode.BASIC_EPS,
        "reported_basic_eps",
        ("reported_basic_eps",),
        period="EXACT_REPORTED_DURATION",
        currency="PER_SHARE_CURRENCY",
    ),
    _definition(
        MetricCode.DILUTED_EPS,
        "reported_diluted_eps",
        ("reported_diluted_eps",),
        period="EXACT_REPORTED_DURATION",
        currency="PER_SHARE_CURRENCY",
    ),
    _definition(
        MetricCode.MARKET_CAP,
        "price * actual_shares_outstanding",
        ("price", "actual_shares_outstanding"),
        period="PRICE_DATE",
        currency="PRICE_CURRENCY",
        denominator="POSITIVE_PRICE_AND_SHARES",
    ),
    _definition(
        MetricCode.PE_TTM_DILUTED,
        "market_cap / net_income_parent_ttm",
        ("market_cap", "net_income_parent_ttm"),
        period="POINT_IN_TIME_OVER_TTM",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.PB_PARENT,
        "market_cap / equity_parent",
        ("market_cap", "equity_parent"),
        period="POINT_IN_TIME",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.PS_TTM,
        "market_cap / revenue_ttm",
        ("market_cap", "revenue_ttm"),
        period="POINT_IN_TIME_OVER_TTM",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.ENTERPRISE_VALUE,
        "market_cap + total_debt + preferred_equity + minority_interest - cash",
        ("market_cap", "total_debt", "preferred_equity", "minority_interest", "cash"),
        period="POINT_IN_TIME",
    ),
    _definition(
        MetricCode.EV_TO_EBITDA_TTM,
        "enterprise_value / ebitda_ttm",
        ("enterprise_value", "ebitda_ttm"),
        period="POINT_IN_TIME_OVER_TTM",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.FCF_YIELD_TTM,
        "free_cash_flow_ttm / market_cap",
        ("free_cash_flow_ttm", "market_cap"),
        period="POINT_IN_TIME_OVER_TTM",
        denominator="NON_POSITIVE_IS_NM",
    ),
    _definition(
        MetricCode.REVENUE_TTM,
        "four quarters OR latest_fy + latest_ytd - prior_ytd",
        ("quarter_1", "quarter_2", "quarter_3", "quarter_4"),
        period="FOUR_COMPARABLE_QUARTERS",
        optional=("latest_fy", "latest_ytd", "prior_ytd"),
    ),
    _definition(
        MetricCode.NET_INCOME_PARENT_TTM,
        "four quarters OR latest_fy + latest_ytd - prior_ytd",
        ("quarter_1", "quarter_2", "quarter_3", "quarter_4"),
        period="FOUR_COMPARABLE_QUARTERS",
        optional=("latest_fy", "latest_ytd", "prior_ytd"),
    ),
    _definition(
        MetricCode.EBITDA_TTM,
        "four quarters OR latest_fy + latest_ytd - prior_ytd",
        ("quarter_1", "quarter_2", "quarter_3", "quarter_4"),
        period="FOUR_COMPARABLE_QUARTERS",
        optional=("latest_fy", "latest_ytd", "prior_ytd"),
    ),
)

_FORMULA_BY_CODE = {definition.metric_code: definition for definition in FORMULA_REGISTRY}

if len(_FORMULA_BY_CODE) != len(MetricCode):
    raise RuntimeError("formula registry is incomplete or duplicated")


def get_formula(metric_code: MetricCode | str) -> FormulaDefinition:
    try:
        code = MetricCode(metric_code)
        return _FORMULA_BY_CODE[code]
    except (KeyError, ValueError):
        raise KeyError(metric_code) from None


class _FormulaBlocked(Exception):
    def __init__(self, warning: str) -> None:
        self.warning = warning


def _required(
    inputs: Mapping[str, FormulaInput],
    roles: tuple[str, ...],
) -> tuple[FormulaInput, ...]:
    values: list[FormulaInput] = []
    for role in roles:
        item = inputs.get(role)
        if item is None or item.value is None:
            raise _FormulaBlocked(f"SOURCE_MISSING:{role}")
        values.append(item)
    return tuple(values)


def _same_amount_basis(values: tuple[FormulaInput, ...]) -> tuple[str, str]:
    currencies = {value.currency_code for value in values}
    if None in currencies or len(currencies) != 1:
        raise _FormulaBlocked("INCOMPATIBLE_CURRENCY")
    units = {value.unit for value in values}
    if len(units) != 1:
        raise _FormulaBlocked("INCOMPATIBLE_UNIT")
    currency = next(iter(currencies))
    if currency is None:
        raise _FormulaBlocked("INCOMPATIBLE_CURRENCY")
    return currency, next(iter(units))


def _numeric(
    code: MetricCode,
    value: Decimal,
    *,
    unit: str,
    currency_code: str | None,
    roles: tuple[str, ...],
    warnings: tuple[str, ...] = (),
) -> MetricResult:
    return MetricResult(
        metric_code=code,
        value=value,
        value_state=MetricValueState.ZERO if value == 0 else MetricValueState.VALUE,
        unit=unit,
        currency_code=currency_code,
        quality_status=QualityStatus.PARTIAL if warnings else QualityStatus.PASS,
        formula_version=get_formula(code).formula_version,
        warnings=warnings,
        consumed_inputs=roles,
    )


def _non_numeric(
    code: MetricCode,
    state: MetricValueState,
    warning: str,
    *,
    roles: tuple[str, ...] = (),
) -> MetricResult:
    amount_outputs = {
        MetricCode.OPERATING_CASH_FLOW,
        MetricCode.FREE_CASH_FLOW,
        MetricCode.NET_DEBT,
        MetricCode.MARKET_CAP,
        MetricCode.ENTERPRISE_VALUE,
        MetricCode.REVENUE_TTM,
        MetricCode.NET_INCOME_PARENT_TTM,
        MetricCode.EBITDA_TTM,
    }
    per_share_outputs = {MetricCode.BASIC_EPS, MetricCode.DILUTED_EPS}
    unit = (
        "ONE" if code in amount_outputs else "PER_SHARE" if code in per_share_outputs else "RATIO"
    )
    return MetricResult(
        metric_code=code,
        value=None,
        value_state=state,
        unit=unit,
        currency_code=None,
        quality_status=(
            QualityStatus.BLOCKED if state is MetricValueState.NULL else QualityStatus.PASS
        ),
        formula_version=get_formula(code).formula_version,
        warnings=(warning,),
        consumed_inputs=roles,
    )


def _ratio_formula(
    code: MetricCode,
    inputs: Mapping[str, FormulaInput],
    numerator_role: str,
    denominator_role: str,
    *,
    negative_warning: str | None = None,
) -> MetricResult:
    roles = (numerator_role, denominator_role)
    numerator, denominator = _required(inputs, roles)
    _same_amount_basis((numerator, denominator))
    assert numerator.value is not None and denominator.value is not None
    if denominator.value <= 0:
        return _non_numeric(
            code,
            MetricValueState.NOT_MEANINGFUL,
            "DENOMINATOR_NON_POSITIVE",
            roles=roles,
        )
    result = numerator.value / denominator.value
    warnings = (negative_warning,) if negative_warning and result < 0 else ()
    return _numeric(code, result, unit="RATIO", currency_code=None, roles=roles, warnings=warnings)


def _revenue_growth(inputs: Mapping[str, FormulaInput]) -> MetricResult:
    roles = ("current_revenue", "prior_revenue")
    current, prior = _required(inputs, roles)
    _same_amount_basis((current, prior))
    assert current.value is not None and prior.value is not None
    if prior.value <= 0:
        return _non_numeric(
            MetricCode.REVENUE_GROWTH,
            MetricValueState.NOT_MEANINGFUL,
            "DENOMINATOR_NON_POSITIVE",
            roles=roles,
        )
    warnings = ("NEGATIVE_CURRENT_REVENUE",) if current.value < 0 else ()
    return _numeric(
        MetricCode.REVENUE_GROWTH,
        (current.value - prior.value) / prior.value,
        unit="RATIO",
        currency_code=None,
        roles=roles,
        warnings=warnings,
    )


def _average_return(
    code: MetricCode,
    inputs: Mapping[str, FormulaInput],
    numerator_role: str,
    opening_role: str,
    closing_role: str,
) -> MetricResult:
    roles = (numerator_role, opening_role, closing_role)
    numerator, opening, closing = _required(inputs, roles)
    _same_amount_basis((numerator, opening, closing))
    assert numerator.value is not None and opening.value is not None and closing.value is not None
    average = (opening.value + closing.value) / Decimal("2")
    if average <= 0:
        return _non_numeric(
            code,
            MetricValueState.NOT_MEANINGFUL,
            "DENOMINATOR_NON_POSITIVE",
            roles=roles,
        )
    return _numeric(
        code,
        numerator.value / average,
        unit="RATIO",
        currency_code=None,
        roles=roles,
    )


def _roic(inputs: Mapping[str, FormulaInput]) -> MetricResult:
    roles = get_formula(MetricCode.ROIC).required_inputs
    values = _required(inputs, roles)
    _same_amount_basis(values)
    by_role = dict(zip(roles, values, strict=True))
    raw = {role: value.value for role, value in by_role.items()}
    if any(value is None for value in raw.values()):
        raise _FormulaBlocked("SOURCE_MISSING")
    value = {role: item for role, item in raw.items() if item is not None}
    pretax = value["pretax_income"]
    tax = value["income_tax_expense"]
    if pretax <= 0:
        return _non_numeric(
            MetricCode.ROIC,
            MetricValueState.NULL,
            "EFFECTIVE_TAX_RATE_UNUSABLE",
            roles=roles,
        )
    tax_rate = tax / pretax
    if tax_rate < 0 or tax_rate > 1:
        return _non_numeric(
            MetricCode.ROIC,
            MetricValueState.NULL,
            "EFFECTIVE_TAX_RATE_UNUSABLE",
            roles=roles,
        )
    opening_capital = (
        value["opening_total_equity"] + value["opening_total_debt"] - value["opening_cash"]
    )
    closing_capital = (
        value["closing_total_equity"] + value["closing_total_debt"] - value["closing_cash"]
    )
    average_capital = (opening_capital + closing_capital) / Decimal("2")
    if average_capital <= 0:
        return _non_numeric(
            MetricCode.ROIC,
            MetricValueState.NOT_MEANINGFUL,
            "DENOMINATOR_NON_POSITIVE",
            roles=roles,
        )
    nopat = value["operating_income"] * (Decimal("1") - tax_rate)
    return _numeric(
        MetricCode.ROIC,
        nopat / average_capital,
        unit="RATIO",
        currency_code=None,
        roles=roles,
    )


def _signed_amount(
    code: MetricCode,
    inputs: Mapping[str, FormulaInput],
    roles: tuple[str, ...],
    operation: Callable[[tuple[Decimal, ...]], Decimal],
) -> MetricResult:
    values = _required(inputs, roles)
    currency, unit = _same_amount_basis(values)
    exact = tuple(value.value for value in values)
    assert all(value is not None for value in exact)
    decimals = tuple(value for value in exact if value is not None)
    return _numeric(
        code,
        operation(decimals),
        unit=unit,
        currency_code=currency,
        roles=roles,
    )


def _ttm_amount(
    code: MetricCode,
    inputs: Mapping[str, FormulaInput],
) -> MetricResult:
    quarter_roles = ("quarter_1", "quarter_2", "quarter_3", "quarter_4")
    bridge_roles = ("latest_fy", "latest_ytd", "prior_ytd")
    if all(role in inputs for role in quarter_roles):
        return _signed_amount(
            code,
            inputs,
            quarter_roles,
            lambda values: sum(values, start=Decimal("0")),
        )
    if all(role in inputs for role in bridge_roles):
        return _signed_amount(
            code,
            inputs,
            bridge_roles,
            lambda values: values[0] + values[1] - values[2],
        )
    raise _FormulaBlocked("SOURCE_MISSING:TTM_COMPARABLE_INPUT_SET")


def _reported_eps(code: MetricCode, role: str, inputs: Mapping[str, FormulaInput]) -> MetricResult:
    (value,) = _required(inputs, (role,))
    if value.unit != "PER_SHARE" or value.currency_code is None:
        raise _FormulaBlocked("INCOMPATIBLE_UNIT")
    assert value.value is not None
    return _numeric(
        code,
        value.value,
        unit="PER_SHARE",
        currency_code=value.currency_code,
        roles=(role,),
    )


def _market_cap(inputs: Mapping[str, FormulaInput]) -> MetricResult:
    roles = ("price", "actual_shares_outstanding")
    price, shares = _required(inputs, roles)
    if price.unit != "PER_SHARE" or shares.unit != "SHARES":
        raise _FormulaBlocked("INCOMPATIBLE_UNIT")
    if price.currency_code is None or shares.currency_code is not None:
        raise _FormulaBlocked("INCOMPATIBLE_CURRENCY")
    assert price.value is not None and shares.value is not None
    if price.value <= 0 or shares.value <= 0:
        return _non_numeric(
            MetricCode.MARKET_CAP,
            MetricValueState.NOT_MEANINGFUL,
            "NON_POSITIVE_PRICE_OR_SHARES",
            roles=roles,
        )
    return _numeric(
        MetricCode.MARKET_CAP,
        price.value * shares.value,
        unit="ONE",
        currency_code=price.currency_code,
        roles=roles,
    )


def _enterprise_value(inputs: Mapping[str, FormulaInput]) -> MetricResult:
    roles = get_formula(MetricCode.ENTERPRISE_VALUE).required_inputs
    values = _required(inputs, roles)
    currency, unit = _same_amount_basis(values)
    exact = tuple(value.value for value in values)
    assert all(value is not None for value in exact)
    market_cap, debt, preferred, minority, cash = (value for value in exact if value is not None)
    result = market_cap + debt + preferred + minority - cash
    warnings = ("NEGATIVE_ENTERPRISE_VALUE",) if result < 0 else ()
    return _numeric(
        MetricCode.ENTERPRISE_VALUE,
        result,
        unit=unit,
        currency_code=currency,
        roles=roles,
        warnings=warnings,
    )


def _ev_to_ebitda(inputs: Mapping[str, FormulaInput]) -> MetricResult:
    result = _ratio_formula(
        MetricCode.EV_TO_EBITDA_TTM,
        inputs,
        "enterprise_value",
        "ebitda_ttm",
    )
    if result.value is not None and result.value < 0:
        return MetricResult(
            **{
                **result.__dict__,
                "quality_status": QualityStatus.PARTIAL,
                "warnings": ("NEGATIVE_ENTERPRISE_VALUE",),
            }
        )
    return result


def _liabilities_to_assets(inputs: Mapping[str, FormulaInput]) -> MetricResult:
    liabilities = inputs.get("total_liabilities")
    if liabilities is not None and liabilities.value is not None and liabilities.value < 0:
        return _non_numeric(
            MetricCode.LIABILITIES_TO_ASSETS,
            MetricValueState.NULL,
            "NEGATIVE_LIABILITIES_REJECTED",
        )
    return _ratio_formula(
        MetricCode.LIABILITIES_TO_ASSETS,
        inputs,
        "total_liabilities",
        "total_assets",
    )


def _gross_margin(inputs: Mapping[str, FormulaInput]) -> MetricResult:
    roles = ("revenue", "cost_of_revenue")
    revenue, cost = _required(inputs, roles)
    _same_amount_basis((revenue, cost))
    assert revenue.value is not None and cost.value is not None
    if revenue.value <= 0:
        return _non_numeric(
            MetricCode.GROSS_MARGIN,
            MetricValueState.NOT_MEANINGFUL,
            "DENOMINATOR_NON_POSITIVE",
            roles=roles,
        )
    result = (revenue.value - cost.value) / revenue.value
    warnings = ("NEGATIVE_GROSS_MARGIN",) if result < 0 else ()
    return _numeric(
        MetricCode.GROSS_MARGIN,
        result,
        unit="RATIO",
        currency_code=None,
        roles=roles,
        warnings=warnings,
    )


_IMPLEMENTATIONS: dict[MetricCode, Callable[[Mapping[str, FormulaInput]], MetricResult]] = {
    MetricCode.REVENUE_GROWTH: _revenue_growth,
    MetricCode.GROSS_MARGIN: _gross_margin,
    MetricCode.OPERATING_MARGIN: lambda inputs: _ratio_formula(
        MetricCode.OPERATING_MARGIN,
        inputs,
        "operating_income",
        "revenue",
        negative_warning="NEGATIVE_OPERATING_MARGIN",
    ),
    MetricCode.NET_MARGIN_PARENT: lambda inputs: _ratio_formula(
        MetricCode.NET_MARGIN_PARENT,
        inputs,
        "net_income_parent",
        "revenue",
        negative_warning="NEGATIVE_NET_MARGIN",
    ),
    MetricCode.ROE_PARENT: lambda inputs: _average_return(
        MetricCode.ROE_PARENT,
        inputs,
        "net_income_parent",
        "opening_equity_parent",
        "closing_equity_parent",
    ),
    MetricCode.ROA_TOTAL: lambda inputs: _average_return(
        MetricCode.ROA_TOTAL,
        inputs,
        "net_income_total",
        "opening_total_assets",
        "closing_total_assets",
    ),
    MetricCode.ROIC: _roic,
    MetricCode.OPERATING_CASH_FLOW: lambda inputs: _signed_amount(
        MetricCode.OPERATING_CASH_FLOW,
        inputs,
        ("reported_ocf",),
        lambda values: values[0],
    ),
    MetricCode.FREE_CASH_FLOW: lambda inputs: _signed_amount(
        MetricCode.FREE_CASH_FLOW,
        inputs,
        ("operating_cash_flow", "capital_expenditures"),
        lambda values: values[0] - values[1],
    ),
    MetricCode.LIABILITIES_TO_ASSETS: _liabilities_to_assets,
    MetricCode.NET_DEBT: lambda inputs: _signed_amount(
        MetricCode.NET_DEBT,
        inputs,
        ("total_debt", "cash"),
        lambda values: values[0] - values[1],
    ),
    MetricCode.BASIC_EPS: lambda inputs: _reported_eps(
        MetricCode.BASIC_EPS, "reported_basic_eps", inputs
    ),
    MetricCode.DILUTED_EPS: lambda inputs: _reported_eps(
        MetricCode.DILUTED_EPS, "reported_diluted_eps", inputs
    ),
    MetricCode.MARKET_CAP: _market_cap,
    MetricCode.PE_TTM_DILUTED: lambda inputs: _ratio_formula(
        MetricCode.PE_TTM_DILUTED,
        inputs,
        "market_cap",
        "net_income_parent_ttm",
    ),
    MetricCode.PB_PARENT: lambda inputs: _ratio_formula(
        MetricCode.PB_PARENT,
        inputs,
        "market_cap",
        "equity_parent",
    ),
    MetricCode.PS_TTM: lambda inputs: _ratio_formula(
        MetricCode.PS_TTM,
        inputs,
        "market_cap",
        "revenue_ttm",
    ),
    MetricCode.ENTERPRISE_VALUE: _enterprise_value,
    MetricCode.EV_TO_EBITDA_TTM: _ev_to_ebitda,
    MetricCode.FCF_YIELD_TTM: lambda inputs: _ratio_formula(
        MetricCode.FCF_YIELD_TTM,
        inputs,
        "free_cash_flow_ttm",
        "market_cap",
    ),
    MetricCode.REVENUE_TTM: lambda inputs: _ttm_amount(MetricCode.REVENUE_TTM, inputs),
    MetricCode.NET_INCOME_PARENT_TTM: lambda inputs: _ttm_amount(
        MetricCode.NET_INCOME_PARENT_TTM, inputs
    ),
    MetricCode.EBITDA_TTM: lambda inputs: _ttm_amount(MetricCode.EBITDA_TTM, inputs),
}


def execute_formula(
    metric_code: MetricCode | str,
    inputs: Mapping[str, FormulaInput],
) -> MetricResult:
    """Execute one fixed implementation; text expressions are audit metadata only."""

    definition = get_formula(metric_code)
    try:
        return _IMPLEMENTATIONS[definition.metric_code](inputs)
    except _FormulaBlocked as error:
        return _non_numeric(
            definition.metric_code,
            MetricValueState.NULL,
            error.warning,
        )
