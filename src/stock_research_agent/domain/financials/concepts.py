"""Versioned provider-neutral financial concept registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from stock_research_agent.domain.financials.enums import (
    ConceptStatus,
    FactNature,
    StatementType,
    UnitType,
)


class CanonicalConcept(StrEnum):
    REVENUE = "REVENUE"
    COST_OF_REVENUE = "COST_OF_REVENUE"
    GROSS_PROFIT = "GROSS_PROFIT"
    OPERATING_INCOME = "OPERATING_INCOME"
    EBITDA = "EBITDA"
    PRETAX_INCOME = "PRETAX_INCOME"
    INCOME_TAX_EXPENSE = "INCOME_TAX_EXPENSE"
    NET_INCOME = "NET_INCOME"
    NET_INCOME_ATTRIBUTABLE_TO_PARENT = "NET_INCOME_ATTRIBUTABLE_TO_PARENT"
    BASIC_EPS = "BASIC_EPS"
    DILUTED_EPS = "DILUTED_EPS"
    CASH_AND_CASH_EQUIVALENTS = "CASH_AND_CASH_EQUIVALENTS"
    SHORT_TERM_INVESTMENTS = "SHORT_TERM_INVESTMENTS"
    ACCOUNTS_RECEIVABLE = "ACCOUNTS_RECEIVABLE"
    INVENTORY = "INVENTORY"
    TOTAL_CURRENT_ASSETS = "TOTAL_CURRENT_ASSETS"
    TOTAL_ASSETS = "TOTAL_ASSETS"
    SHORT_TERM_DEBT = "SHORT_TERM_DEBT"
    LONG_TERM_DEBT = "LONG_TERM_DEBT"
    TOTAL_DEBT = "TOTAL_DEBT"
    TOTAL_CURRENT_LIABILITIES = "TOTAL_CURRENT_LIABILITIES"
    TOTAL_LIABILITIES = "TOTAL_LIABILITIES"
    TOTAL_EQUITY = "TOTAL_EQUITY"
    EQUITY_ATTRIBUTABLE_TO_PARENT = "EQUITY_ATTRIBUTABLE_TO_PARENT"
    MINORITY_INTEREST = "MINORITY_INTEREST"
    PREFERRED_EQUITY = "PREFERRED_EQUITY"
    OPERATING_CASH_FLOW = "OPERATING_CASH_FLOW"
    CAPITAL_EXPENDITURES = "CAPITAL_EXPENDITURES"
    INVESTING_CASH_FLOW = "INVESTING_CASH_FLOW"
    FINANCING_CASH_FLOW = "FINANCING_CASH_FLOW"
    CASH_DIVIDENDS_PAID = "CASH_DIVIDENDS_PAID"
    SHARE_REPURCHASES = "SHARE_REPURCHASES"
    BASIC_WEIGHTED_AVERAGE_SHARES = "BASIC_WEIGHTED_AVERAGE_SHARES"
    DILUTED_WEIGHTED_AVERAGE_SHARES = "DILUTED_WEIGHTED_AVERAGE_SHARES"
    PERIOD_END_SHARES_OUTSTANDING = "PERIOD_END_SHARES_OUTSTANDING"


@dataclass(frozen=True)
class CanonicalConceptDefinition:
    code: CanonicalConcept
    name: str
    statement_type: StatementType
    fact_nature: FactNature
    default_unit_type: UnitType
    supports_duration: bool
    supports_instant: bool
    supports_cumulative: bool
    supports_ttm: bool
    allows_negative: bool
    description: str
    version: str = "1.0.0"
    status: ConceptStatus = ConceptStatus.ACTIVE


_INCOME_AMOUNT_CONCEPTS = (
    CanonicalConcept.REVENUE,
    CanonicalConcept.COST_OF_REVENUE,
    CanonicalConcept.GROSS_PROFIT,
    CanonicalConcept.OPERATING_INCOME,
    CanonicalConcept.EBITDA,
    CanonicalConcept.PRETAX_INCOME,
    CanonicalConcept.INCOME_TAX_EXPENSE,
    CanonicalConcept.NET_INCOME,
    CanonicalConcept.NET_INCOME_ATTRIBUTABLE_TO_PARENT,
)
_BALANCE_CONCEPTS = (
    CanonicalConcept.CASH_AND_CASH_EQUIVALENTS,
    CanonicalConcept.SHORT_TERM_INVESTMENTS,
    CanonicalConcept.ACCOUNTS_RECEIVABLE,
    CanonicalConcept.INVENTORY,
    CanonicalConcept.TOTAL_CURRENT_ASSETS,
    CanonicalConcept.TOTAL_ASSETS,
    CanonicalConcept.SHORT_TERM_DEBT,
    CanonicalConcept.LONG_TERM_DEBT,
    CanonicalConcept.TOTAL_DEBT,
    CanonicalConcept.TOTAL_CURRENT_LIABILITIES,
    CanonicalConcept.TOTAL_LIABILITIES,
    CanonicalConcept.TOTAL_EQUITY,
    CanonicalConcept.EQUITY_ATTRIBUTABLE_TO_PARENT,
    CanonicalConcept.MINORITY_INTEREST,
    CanonicalConcept.PREFERRED_EQUITY,
)
_CASH_FLOW_CONCEPTS = (
    CanonicalConcept.OPERATING_CASH_FLOW,
    CanonicalConcept.CAPITAL_EXPENDITURES,
    CanonicalConcept.INVESTING_CASH_FLOW,
    CanonicalConcept.FINANCING_CASH_FLOW,
    CanonicalConcept.CASH_DIVIDENDS_PAID,
    CanonicalConcept.SHARE_REPURCHASES,
)


def _label(code: CanonicalConcept) -> str:
    return code.value.replace("_", " ").title()


def _duration_amount(
    code: CanonicalConcept, statement: StatementType
) -> CanonicalConceptDefinition:
    return CanonicalConceptDefinition(
        code=code,
        name=_label(code),
        statement_type=statement,
        fact_nature=FactNature.DURATION,
        default_unit_type=UnitType.MONETARY_AMOUNT,
        supports_duration=True,
        supports_instant=False,
        supports_cumulative=True,
        supports_ttm=True,
        allows_negative=code
        not in {
            CanonicalConcept.REVENUE,
            CanonicalConcept.COST_OF_REVENUE,
            CanonicalConcept.INCOME_TAX_EXPENSE,
        },
        description=f"Canonical reported {_label(code).lower()} amount for a duration period.",
    )


def _instant_amount(code: CanonicalConcept) -> CanonicalConceptDefinition:
    return CanonicalConceptDefinition(
        code=code,
        name=_label(code),
        statement_type=StatementType.BALANCE_SHEET,
        fact_nature=FactNature.INSTANT,
        default_unit_type=UnitType.MONETARY_AMOUNT,
        supports_duration=False,
        supports_instant=True,
        supports_cumulative=False,
        supports_ttm=False,
        allows_negative=code
        in {
            CanonicalConcept.TOTAL_EQUITY,
            CanonicalConcept.EQUITY_ATTRIBUTABLE_TO_PARENT,
        },
        description=f"Canonical reported {_label(code).lower()} amount at a point in time.",
    )


def _per_share(code: CanonicalConcept) -> CanonicalConceptDefinition:
    return CanonicalConceptDefinition(
        code=code,
        name=_label(code),
        statement_type=StatementType.INCOME_STATEMENT,
        fact_nature=FactNature.PER_SHARE,
        default_unit_type=UnitType.PER_SHARE,
        supports_duration=True,
        supports_instant=False,
        supports_cumulative=False,
        supports_ttm=False,
        allows_negative=True,
        description=f"Canonical reported {_label(code).lower()} for a duration period.",
    )


def _shares(code: CanonicalConcept, *, instant: bool) -> CanonicalConceptDefinition:
    return CanonicalConceptDefinition(
        code=code,
        name=_label(code),
        statement_type=StatementType.SHARES,
        fact_nature=FactNature.SHARES,
        default_unit_type=UnitType.SHARES,
        supports_duration=not instant,
        supports_instant=instant,
        supports_cumulative=False,
        supports_ttm=False,
        allows_negative=False,
        description=(
            f"Canonical reported {_label(code).lower()} "
            f"for a {'point in time' if instant else 'duration period'}."
        ),
    )


CANONICAL_CONCEPTS: tuple[CanonicalConceptDefinition, ...] = (
    *(_duration_amount(code, StatementType.INCOME_STATEMENT) for code in _INCOME_AMOUNT_CONCEPTS),
    _per_share(CanonicalConcept.BASIC_EPS),
    _per_share(CanonicalConcept.DILUTED_EPS),
    *(_instant_amount(code) for code in _BALANCE_CONCEPTS),
    *(_duration_amount(code, StatementType.CASH_FLOW) for code in _CASH_FLOW_CONCEPTS),
    _shares(CanonicalConcept.BASIC_WEIGHTED_AVERAGE_SHARES, instant=False),
    _shares(CanonicalConcept.DILUTED_WEIGHTED_AVERAGE_SHARES, instant=False),
    _shares(CanonicalConcept.PERIOD_END_SHARES_OUTSTANDING, instant=True),
)

_CONCEPT_BY_CODE = {definition.code: definition for definition in CANONICAL_CONCEPTS}

if len(_CONCEPT_BY_CODE) != len(CanonicalConcept):
    raise RuntimeError("canonical financial concept registry is incomplete or duplicated")


def get_concept(code: CanonicalConcept | str) -> CanonicalConceptDefinition:
    """Return one exact registered concept; unknown codes are never approximated."""

    return _CONCEPT_BY_CODE[CanonicalConcept(code)]
