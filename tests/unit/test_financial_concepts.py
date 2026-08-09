from __future__ import annotations

from datetime import date

import pytest

from stock_research_agent.domain.financials.concepts import (
    CANONICAL_CONCEPTS,
    CanonicalConcept,
    CanonicalConceptDefinition,
    get_concept,
)
from stock_research_agent.domain.financials.enums import (
    FactNature,
    MappingStatus,
    StatementType,
    UnitType,
)
from stock_research_agent.domain.financials.mapping import (
    FactMappingInput,
    ProviderFactMappingRule,
    resolve_fact_mapping,
)

EXPECTED_CONCEPT_CODES = {
    "REVENUE",
    "COST_OF_REVENUE",
    "GROSS_PROFIT",
    "OPERATING_INCOME",
    "EBITDA",
    "PRETAX_INCOME",
    "INCOME_TAX_EXPENSE",
    "NET_INCOME",
    "NET_INCOME_ATTRIBUTABLE_TO_PARENT",
    "BASIC_EPS",
    "DILUTED_EPS",
    "CASH_AND_CASH_EQUIVALENTS",
    "SHORT_TERM_INVESTMENTS",
    "ACCOUNTS_RECEIVABLE",
    "INVENTORY",
    "TOTAL_CURRENT_ASSETS",
    "TOTAL_ASSETS",
    "SHORT_TERM_DEBT",
    "LONG_TERM_DEBT",
    "TOTAL_DEBT",
    "TOTAL_CURRENT_LIABILITIES",
    "TOTAL_LIABILITIES",
    "TOTAL_EQUITY",
    "EQUITY_ATTRIBUTABLE_TO_PARENT",
    "MINORITY_INTEREST",
    "PREFERRED_EQUITY",
    "OPERATING_CASH_FLOW",
    "CAPITAL_EXPENDITURES",
    "INVESTING_CASH_FLOW",
    "FINANCING_CASH_FLOW",
    "CASH_DIVIDENDS_PAID",
    "SHARE_REPURCHASES",
    "BASIC_WEIGHTED_AVERAGE_SHARES",
    "DILUTED_WEIGHTED_AVERAGE_SHARES",
    "PERIOD_END_SHARES_OUTSTANDING",
}


def test_canonical_registry_contains_exact_required_stage5_concepts() -> None:
    assert {concept.code for concept in CANONICAL_CONCEPTS} == EXPECTED_CONCEPT_CODES
    assert len(CANONICAL_CONCEPTS) == len(EXPECTED_CONCEPT_CODES)


def test_concept_metadata_keeps_semantically_distinct_inputs_separate() -> None:
    parent_income = get_concept(CanonicalConcept.NET_INCOME_ATTRIBUTABLE_TO_PARENT)
    total_income = get_concept(CanonicalConcept.NET_INCOME)
    basic_eps = get_concept(CanonicalConcept.BASIC_EPS)
    diluted_eps = get_concept(CanonicalConcept.DILUTED_EPS)
    period_end_shares = get_concept(CanonicalConcept.PERIOD_END_SHARES_OUTSTANDING)
    weighted_shares = get_concept(CanonicalConcept.BASIC_WEIGHTED_AVERAGE_SHARES)

    assert parent_income.code != total_income.code
    assert basic_eps.code != diluted_eps.code
    assert period_end_shares.fact_nature is FactNature.SHARES
    assert weighted_shares.fact_nature is FactNature.SHARES
    assert period_end_shares.supports_instant is True
    assert period_end_shares.supports_duration is False
    assert weighted_shares.supports_duration is True
    assert weighted_shares.supports_instant is False


@pytest.mark.parametrize("concept", CANONICAL_CONCEPTS, ids=lambda value: value.code)
def test_every_concept_has_versioned_complete_metadata(
    concept: CanonicalConceptDefinition,
) -> None:
    assert concept.version == "1.0.0"
    assert concept.name
    assert concept.description
    assert isinstance(concept.statement_type, StatementType)
    assert isinstance(concept.fact_nature, FactNature)
    assert isinstance(concept.default_unit_type, UnitType)
    assert concept.supports_duration or concept.supports_instant


def _mapping_rule(
    *,
    provider_concept: str = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    canonical_concept: CanonicalConcept = CanonicalConcept.REVENUE,
    status: MappingStatus = MappingStatus.APPROVED,
    form_type: str | None = "10-K",
) -> ProviderFactMappingRule:
    return ProviderFactMappingRule(
        rule_id=f"sec-us-gaap-{canonical_concept.value.lower()}-v1",
        provider_code="SEC_ARCHIVES",
        provider_concept=provider_concept,
        taxonomy="us-gaap/2025",
        statement_type=StatementType.INCOME_STATEMENT,
        form_type=form_type,
        context_rules=("CONSOLIDATED",),
        dimension_rules=(),
        canonical_concept=canonical_concept,
        status=status,
        mapping_version="1.0.0",
        valid_from=date(2025, 1, 1),
        valid_to=None,
        source_reference="SEC taxonomy review 2025-01-01",
        reviewed_by="stage-5-fixture-review",
    )


def _mapping_input(
    *,
    provider_concept: str = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    form_type: str = "10-K",
) -> FactMappingInput:
    return FactMappingInput(
        provider_code="SEC_ARCHIVES",
        provider_concept=provider_concept,
        taxonomy="us-gaap/2025",
        statement_type=StatementType.INCOME_STATEMENT,
        form_type=form_type,
        contexts=("CONSOLIDATED",),
        dimensions=(),
        source_published_on=date(2026, 2, 1),
    )


def test_mapping_requires_exact_provider_taxonomy_form_and_context() -> None:
    rule = _mapping_rule()

    resolved = resolve_fact_mapping(_mapping_input(), (rule,))
    wrong_form = resolve_fact_mapping(_mapping_input(form_type="10-Q"), (rule,))
    similar_label = resolve_fact_mapping(
        _mapping_input(provider_concept="RevenueFromContractWithCustomer"),
        (rule,),
    )

    assert resolved.status is MappingStatus.APPROVED
    assert resolved.canonical_concept is CanonicalConcept.REVENUE
    assert resolved.rule_ids == (rule.rule_id,)
    assert wrong_form.status is MappingStatus.UNMAPPED
    assert similar_label.status is MappingStatus.UNMAPPED


def test_multiple_approved_exact_rules_are_ambiguous_not_guessed() -> None:
    revenue = _mapping_rule()
    gross_profit = _mapping_rule(canonical_concept=CanonicalConcept.GROSS_PROFIT)

    result = resolve_fact_mapping(_mapping_input(), (gross_profit, revenue))

    assert result.status is MappingStatus.AMBIGUOUS
    assert result.canonical_concept is None
    assert result.rule_ids == tuple(sorted((revenue.rule_id, gross_profit.rule_id)))


def test_deprecated_mapping_is_not_used_for_new_normalization() -> None:
    result = resolve_fact_mapping(
        _mapping_input(),
        (_mapping_rule(status=MappingStatus.DEPRECATED),),
    )

    assert result.status is MappingStatus.UNMAPPED
    assert result.canonical_concept is None


def test_approved_mapping_requires_review_evidence() -> None:
    with pytest.raises(ValueError, match="source_reference"):
        ProviderFactMappingRule(
            **{
                **_mapping_rule().__dict__,
                "source_reference": "",
            }
        )
