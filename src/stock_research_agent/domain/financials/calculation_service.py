"""Immutable orchestration for deterministic financial metric calculations."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from stock_research_agent.domain.financials.enums import QualityStatus
from stock_research_agent.domain.financials.formulas import (
    FORMULA_REGISTRY,
    FormulaDefinition,
    FormulaInput,
    MetricCode,
    execute_formula,
)
from stock_research_agent.domain.financials.repositories import (
    FinancialCalculationRepository,
)
from stock_research_agent.domain.financials.schemas import (
    CalculationInputWrite,
    CalculationResult,
    CalculationRunWrite,
    DerivedMetricWrite,
    NormalizedFactForCalculation,
)

CALCULATION_VERSION = "1.0.0"
FORMULA_SET_VERSION = "1.0.0"
MAPPING_VERSION = "1.0.0"
NORMALIZATION_VERSION = "1.0.0"

_AMOUNT_METRICS = {
    MetricCode.OPERATING_CASH_FLOW,
    MetricCode.FREE_CASH_FLOW,
    MetricCode.NET_DEBT,
    MetricCode.MARKET_CAP,
    MetricCode.ENTERPRISE_VALUE,
    MetricCode.REVENUE_TTM,
    MetricCode.NET_INCOME_PARENT_TTM,
    MetricCode.EBITDA_TTM,
}
_PER_SHARE_METRICS = {MetricCode.BASIC_EPS, MetricCode.DILUTED_EPS}


class MetricCalculationService:
    """Create or reuse one terminal calculation run for a fixed snapshot input set."""

    def calculate_snapshot(
        self,
        snapshot_id: UUID,
        repository: FinancialCalculationRepository,
    ) -> CalculationResult:
        snapshot = repository.get_snapshot_for_calculation(snapshot_id)
        if snapshot is None:
            raise ValueError("snapshot does not exist")
        facts = repository.list_normalized_facts_for_calculation(snapshot_id)
        checksum = _input_checksum(facts)
        repository.acquire_calculation_lock(snapshot_id, checksum)
        existing = repository.find_calculation_run(
            snapshot_id,
            checksum,
            CALCULATION_VERSION,
            FORMULA_SET_VERSION,
            MAPPING_VERSION,
            NORMALIZATION_VERSION,
        )
        if existing is not None:
            return CalculationResult(
                calculation_run_id=existing.id,
                snapshot_id=existing.snapshot_id,
                status=existing.status,
                metric_count=existing.metric_count,
                warning_count=existing.warning_count,
                input_checksum=existing.input_checksum,
            )

        run_id = repository.create_calculation_run(
            CalculationRunWrite(
                security_id=snapshot.security_id,
                snapshot_id=snapshot.snapshot_id,
                status="RUNNING",
                calculation_version=CALCULATION_VERSION,
                formula_set_version=FORMULA_SET_VERSION,
                mapping_version=MAPPING_VERSION,
                normalization_version=NORMALIZATION_VERSION,
                input_checksum=checksum,
                started_at=datetime.now(UTC),
                warning_count=0,
            )
        )
        if not facts:
            warning = "NO_NORMALIZED_FINANCIAL_FACTS"
            for definition in FORMULA_REGISTRY:
                repository.add_derived_metric(
                    DerivedMetricWrite(
                        calculation_run_id=run_id,
                        security_id=snapshot.security_id,
                        snapshot_id=snapshot.snapshot_id,
                        formula_definition_id=repository.get_formula_definition_id(
                            definition.metric_code.value,
                            definition.formula_version,
                        ),
                        metric_code=definition.metric_code.value,
                        metric_period="SNAPSHOT",
                        period_end=None,
                        value=None,
                        value_state="NULL",
                        unit=_output_unit(definition.metric_code),
                        currency_code=None,
                        quality_status=QualityStatus.BLOCKED,
                        formula_version=definition.formula_version,
                        warning_codes=(warning,),
                    )
                )
            warning_count = len(FORMULA_REGISTRY)
            repository.complete_calculation_run(
                run_id,
                QualityStatus.BLOCKED,
                warning_count,
            )
            return CalculationResult(
                calculation_run_id=run_id,
                snapshot_id=snapshot.snapshot_id,
                status=QualityStatus.BLOCKED,
                metric_count=len(FORMULA_REGISTRY),
                warning_count=warning_count,
                input_checksum=checksum,
            )
        warning_count = 0
        statuses: list[QualityStatus] = []
        for definition in FORMULA_REGISTRY:
            formula_inputs, selected = _bind_inputs(definition, facts)
            result = execute_formula(definition.metric_code, formula_inputs)
            reference = max(
                selected.values(),
                key=lambda fact: (fact.period_end, str(fact.id)),
                default=None,
            )
            repository.add_derived_metric(
                DerivedMetricWrite(
                    calculation_run_id=run_id,
                    security_id=snapshot.security_id,
                    snapshot_id=snapshot.snapshot_id,
                    formula_definition_id=repository.get_formula_definition_id(
                        definition.metric_code.value,
                        definition.formula_version,
                    ),
                    metric_code=definition.metric_code.value,
                    metric_period=_metric_period(definition, reference, selected),
                    period_end=reference.period_end if reference else None,
                    value=result.value,
                    value_state=result.value_state.value,
                    unit=result.unit,
                    currency_code=result.currency_code,
                    quality_status=result.quality_status,
                    formula_version=result.formula_version,
                    warning_codes=result.warnings,
                )
            )
            for role, fact in sorted(selected.items()):
                repository.add_calculation_input(
                    CalculationInputWrite(
                        calculation_run_id=run_id,
                        metric_code=definition.metric_code.value,
                        normalized_fact_id=fact.id,
                        source_record_type=None,
                        source_record_id=None,
                        input_role=role,
                        value_used=fact.normalized_value,
                        unit=fact.normalized_unit,
                        currency_code=fact.currency_code,
                    )
                )
            statuses.append(result.quality_status)
            warning_count += len(result.warnings)

        terminal_status = _aggregate_status(statuses)
        repository.complete_calculation_run(run_id, terminal_status, warning_count)
        return CalculationResult(
            calculation_run_id=run_id,
            snapshot_id=snapshot.snapshot_id,
            status=terminal_status,
            metric_count=len(FORMULA_REGISTRY),
            warning_count=warning_count,
            input_checksum=checksum,
        )


def _output_unit(metric_code: MetricCode) -> str:
    if metric_code in _AMOUNT_METRICS:
        return "ONE"
    if metric_code in _PER_SHARE_METRICS:
        return "PER_SHARE"
    return "RATIO"


def _input_checksum(facts: tuple[NormalizedFactForCalculation, ...]) -> str:
    parts = tuple(
        "|".join(
            (
                str(fact.id),
                fact.canonical_concept_code,
                str(fact.financial_period_id),
                format(fact.normalized_value, "f"),
                fact.normalized_unit,
                fact.currency_code or "",
                str(fact.duration_days or ""),
                fact.accounting_standard,
                fact.source_published_at.isoformat(),
            )
        )
        for fact in sorted(facts, key=lambda item: str(item.id))
    )
    return sha256("\n".join(parts).encode("utf-8")).hexdigest()


_ROLE_CONCEPT = {
    "current_revenue": "REVENUE",
    "prior_revenue": "REVENUE",
    "revenue": "REVENUE",
    "cost_of_revenue": "COST_OF_REVENUE",
    "operating_income": "OPERATING_INCOME",
    "net_income_parent": "NET_INCOME_ATTRIBUTABLE_TO_PARENT",
    "net_income_total": "NET_INCOME",
    "opening_equity_parent": "EQUITY_ATTRIBUTABLE_TO_PARENT",
    "closing_equity_parent": "EQUITY_ATTRIBUTABLE_TO_PARENT",
    "opening_total_assets": "TOTAL_ASSETS",
    "closing_total_assets": "TOTAL_ASSETS",
    "opening_total_equity": "TOTAL_EQUITY",
    "closing_total_equity": "TOTAL_EQUITY",
    "opening_total_debt": "TOTAL_DEBT",
    "closing_total_debt": "TOTAL_DEBT",
    "opening_cash": "CASH_AND_CASH_EQUIVALENTS",
    "closing_cash": "CASH_AND_CASH_EQUIVALENTS",
    "reported_ocf": "OPERATING_CASH_FLOW",
    "operating_cash_flow": "OPERATING_CASH_FLOW",
    "capital_expenditures": "CAPITAL_EXPENDITURES",
    "total_liabilities": "TOTAL_LIABILITIES",
    "total_assets": "TOTAL_ASSETS",
    "total_debt": "TOTAL_DEBT",
    "cash": "CASH_AND_CASH_EQUIVALENTS",
    "reported_basic_eps": "BASIC_EPS",
    "reported_diluted_eps": "DILUTED_EPS",
    "actual_shares_outstanding": "PERIOD_END_SHARES_OUTSTANDING",
    "equity_parent": "EQUITY_ATTRIBUTABLE_TO_PARENT",
    "preferred_equity": "PREFERRED_EQUITY",
    "minority_interest": "MINORITY_INTEREST",
}

_TTM_CONCEPT = {
    MetricCode.REVENUE_TTM: "REVENUE",
    MetricCode.NET_INCOME_PARENT_TTM: "NET_INCOME_ATTRIBUTABLE_TO_PARENT",
    MetricCode.EBITDA_TTM: "EBITDA",
}


def _bind_inputs(
    definition: FormulaDefinition,
    facts: tuple[NormalizedFactForCalculation, ...],
) -> tuple[dict[str, FormulaInput], dict[str, NormalizedFactForCalculation]]:
    if definition.metric_code in _TTM_CONCEPT:
        ttm_selected = _bind_ttm_inputs(
            facts,
            _TTM_CONCEPT[definition.metric_code],
        )
        return _formula_inputs(ttm_selected), ttm_selected

    if definition.metric_code is MetricCode.REVENUE_GROWTH:
        revenue = _facts_for_concept(facts, "REVENUE")
        if not revenue:
            return {}, {}
        current = revenue[-1]
        prior = next(
            (
                fact
                for fact in reversed(revenue[:-1])
                if fact.fiscal_year == current.fiscal_year - 1
                and fact.period_type == current.period_type
                and fact.fiscal_quarter == current.fiscal_quarter
                and fact.is_cumulative == current.is_cumulative
            ),
            None,
        )
        revenue_inputs = {"current_revenue": current}
        if prior is not None:
            revenue_inputs["prior_revenue"] = prior
        return _formula_inputs(revenue_inputs), revenue_inputs

    roles = definition.required_inputs
    selected: dict[str, NormalizedFactForCalculation] = {}
    anchor = _latest_anchor(roles, facts)
    for role in roles:
        concept = _ROLE_CONCEPT.get(role)
        if concept is None:
            continue
        candidates = _facts_for_concept(facts, concept)
        if role.startswith("opening_"):
            if len(candidates) >= 2:
                selected[role] = candidates[-2]
        elif role.startswith("closing_"):
            if candidates:
                selected[role] = candidates[-1]
        elif anchor is not None:
            same_period = [
                fact
                for fact in candidates
                if fact.financial_period_id == anchor.financial_period_id
            ]
            if same_period:
                selected[role] = same_period[-1]
        elif candidates:
            selected[role] = candidates[-1]
    return _formula_inputs(selected), selected


def _latest_anchor(
    roles: tuple[str, ...],
    facts: tuple[NormalizedFactForCalculation, ...],
) -> NormalizedFactForCalculation | None:
    for role in roles:
        concept = _ROLE_CONCEPT.get(role)
        if concept is None or role.startswith(("opening_", "closing_")):
            continue
        candidates = _facts_for_concept(facts, concept)
        if candidates:
            return candidates[-1]
    return None


def _bind_ttm_inputs(
    facts: tuple[NormalizedFactForCalculation, ...],
    concept: str,
) -> dict[str, NormalizedFactForCalculation]:
    concept_facts = _facts_for_concept(facts, concept)
    quarters = [
        fact for fact in concept_facts if fact.is_single_quarter and not fact.is_cumulative
    ][-4:]
    if len(quarters) == 4 and _quarters_are_comparable(quarters):
        return {f"quarter_{index}": fact for index, fact in enumerate(quarters, start=1)}

    annuals = [
        fact for fact in concept_facts if fact.period_type == "ANNUAL" and fact.is_cumulative
    ]
    for annual in reversed(annuals):
        latest_candidates = [
            fact
            for fact in concept_facts
            if fact.fiscal_year == annual.fiscal_year + 1
            and fact.is_cumulative
            and fact.period_type != "ANNUAL"
        ]
        for latest_ytd in reversed(latest_candidates):
            prior_candidates = [
                fact
                for fact in concept_facts
                if fact.fiscal_year == annual.fiscal_year
                and fact.fiscal_quarter == latest_ytd.fiscal_quarter
                and fact.period_type == latest_ytd.period_type
                and fact.is_cumulative
                and fact.period_type != "ANNUAL"
            ]
            if not prior_candidates:
                continue
            prior_ytd = prior_candidates[-1]
            bridge = (annual, latest_ytd, prior_ytd)
            if _same_ttm_basis(bridge) and _durations_are_comparable(
                latest_ytd,
                prior_ytd,
            ):
                return {
                    "latest_fy": annual,
                    "latest_ytd": latest_ytd,
                    "prior_ytd": prior_ytd,
                }
    return {}


def _quarters_are_comparable(quarters: list[NormalizedFactForCalculation]) -> bool:
    if not _same_ttm_basis(tuple(quarters)):
        return False
    indexes = []
    for fact in quarters:
        if fact.fiscal_quarter is None:
            return False
        indexes.append(fact.fiscal_year * 4 + fact.fiscal_quarter - 1)
    return all(later == earlier + 1 for earlier, later in zip(indexes, indexes[1:], strict=False))


def _same_ttm_basis(facts: tuple[NormalizedFactForCalculation, ...]) -> bool:
    currencies = {fact.currency_code for fact in facts}
    return (
        len({fact.normalized_unit for fact in facts}) == 1
        and len(currencies) == 1
        and None not in currencies
        and len({fact.accounting_standard for fact in facts}) == 1
    )


def _durations_are_comparable(
    current: NormalizedFactForCalculation,
    comparison: NormalizedFactForCalculation,
) -> bool:
    if current.duration_days is None or comparison.duration_days is None:
        return current.duration_days == comparison.duration_days
    return abs(current.duration_days - comparison.duration_days) <= 7


def _metric_period(
    definition: FormulaDefinition,
    reference: NormalizedFactForCalculation | None,
    selected: dict[str, NormalizedFactForCalculation],
) -> str:
    if definition.metric_code in _TTM_CONCEPT:
        if "quarter_1" in selected:
            return "TTM:FOUR_QUARTERS"
        if "latest_fy" in selected:
            return "TTM:ANNUAL_YTD_BRIDGE"
        return "TTM:BLOCKED"
    return reference.fiscal_period if reference else "SNAPSHOT"


def _facts_for_concept(
    facts: tuple[NormalizedFactForCalculation, ...],
    concept: str,
) -> list[NormalizedFactForCalculation]:
    return sorted(
        (fact for fact in facts if fact.canonical_concept_code == concept),
        key=lambda fact: (fact.period_end, fact.source_published_at, str(fact.id)),
    )


def _formula_inputs(
    selected: dict[str, NormalizedFactForCalculation],
) -> dict[str, FormulaInput]:
    return {
        role: FormulaInput(
            value=fact.normalized_value,
            unit=fact.normalized_unit,
            currency_code=fact.currency_code,
        )
        for role, fact in selected.items()
    }


def _aggregate_status(statuses: list[QualityStatus]) -> QualityStatus:
    if statuses and all(status is QualityStatus.PASS for status in statuses):
        return QualityStatus.PASS
    if any(status in {QualityStatus.PASS, QualityStatus.PARTIAL} for status in statuses):
        return QualityStatus.PARTIAL
    return QualityStatus.BLOCKED
