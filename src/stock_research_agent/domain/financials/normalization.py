"""Deterministic, point-in-time financial fact normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from stock_research_agent.domain.financials.calculations import (
    CalculationBlocked,
    FinancialValue,
    deaccumulate_quarter,
)
from stock_research_agent.domain.financials.concepts import CanonicalConcept
from stock_research_agent.domain.financials.enums import FactNature, QualityStatus
from stock_research_agent.domain.financials.periods import (
    FinancialPeriod,
    PeriodSemanticsError,
    PeriodType,
)
from stock_research_agent.domain.financials.repositories import (
    FinancialNormalizationRepository,
)
from stock_research_agent.domain.financials.schemas import (
    ApprovedFactMapping,
    FinancialNormalizationResult,
    FinancialPeriodWrite,
    NormalizedFactInputWrite,
    NormalizedFinancialFactWrite,
    RawFinancialFactForNormalization,
)
from stock_research_agent.domain.financials.units import (
    ReportedUnit,
    UnitNormalizationBlocked,
    UnitNormalizationResult,
    normalize_unit,
)

NORMALIZATION_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class _ReportedNormalization:
    raw: RawFinancialFactForNormalization
    snapshot_id: UUID
    mapping: ApprovedFactMapping
    period: FinancialPeriod
    period_id: UUID
    normalized_fact_id: UUID
    normalized_value: UnitNormalizationResult


class FinancialNormalizationService:
    """Normalize only facts known by the snapshot research cutoff."""

    def normalize_snapshot(
        self,
        snapshot_id: UUID,
        repository: FinancialNormalizationRepository,
    ) -> FinancialNormalizationResult:
        snapshot = repository.get_snapshot_for_normalization(snapshot_id)
        if snapshot is None:
            return FinancialNormalizationResult(
                snapshot_id=snapshot_id,
                status=QualityStatus.BLOCKED,
                normalized_fact_count=0,
                period_count=0,
                warnings=("SNAPSHOT_NOT_FOUND",),
            )

        facts = repository.list_snapshot_financial_facts(snapshot_id)
        if not facts:
            return FinancialNormalizationResult(
                snapshot_id=snapshot_id,
                status=QualityStatus.BLOCKED,
                normalized_fact_count=0,
                period_count=0,
                warnings=("NO_FINANCIAL_FACTS_IN_SNAPSHOT",),
            )

        warnings: list[str] = []
        eligible_facts = []
        for fact in facts:
            if fact.source_published_at is None:
                warnings.append(f"SOURCE_PUBLISHED_AT_UNKNOWN:{fact.id}")
                continue
            if fact.source_published_at > snapshot.research_as_of_time:
                warnings.append(f"FACT_AFTER_RESEARCH_AS_OF:{fact.id}")
                continue
            eligible_facts.append(fact)

        if not eligible_facts:
            return FinancialNormalizationResult(
                snapshot_id=snapshot_id,
                status=QualityStatus.BLOCKED,
                normalized_fact_count=0,
                period_count=0,
                warnings=tuple(warnings),
            )

        normalized_fact_count = 0
        period_ids: set[UUID] = set()
        reported: list[_ReportedNormalization] = []
        for fact in eligible_facts:
            source_published_at = fact.source_published_at
            assert source_published_at is not None
            mapping = repository.find_approved_fact_mapping(
                fact,
                snapshot.research_as_of_time.date(),
            )
            if mapping is None:
                warnings.append(f"NO_APPROVED_MAPPING:{fact.id}")
                continue
            try:
                period = _build_period(fact, mapping.fact_nature, mapping.accounting_standard)
                unit = normalize_unit(
                    fact.value,
                    ReportedUnit(fact.unit),
                    mapping.default_unit_type,
                )
            except (PeriodSemanticsError, UnitNormalizationBlocked, ValueError) as error:
                warnings.append(f"FACT_NORMALIZATION_BLOCKED:{fact.id}:{error}")
                continue

            period_write = FinancialPeriodWrite(
                security_id=fact.security_id,
                snapshot_id=snapshot.snapshot_id,
                fiscal_year=period.fiscal_year,
                fiscal_quarter=period.fiscal_quarter,
                fiscal_period=period.fiscal_period,
                period_type=period.period_type.value,
                period_start=period.period_start,
                period_end=period.period_end,
                filing_date=period.filing_date,
                published_at=period.published_at,
                duration_days=period.duration_days,
                is_annual=period.is_annual,
                is_cumulative=period.is_cumulative,
                is_single_quarter=period.is_single_quarter,
                is_ttm=period.is_ttm,
                accounting_standard=period.accounting_standard,
                source_form_type=period.source_form_type,
            )
            period_id = repository.get_or_create_financial_period(period_write)
            period_ids.add(period_id)
            normalized_write = NormalizedFinancialFactWrite(
                security_id=fact.security_id,
                snapshot_id=snapshot.snapshot_id,
                financial_period_id=period_id,
                canonical_concept_id=mapping.canonical_concept_id,
                source_financial_fact_id=fact.id,
                mapping_id=mapping.mapping_id,
                original_value=unit.original_value,
                normalized_value=unit.normalized_value,
                original_unit=unit.original_unit.value,
                normalized_unit=unit.normalized_unit,
                currency_code=fact.currency_code,
                scale_factor=unit.scale_factor,
                fact_nature=mapping.fact_nature,
                is_reported=True,
                is_derived_from_cumulative=False,
                is_restated=fact.is_restated,
                source_published_at=source_published_at,
                mapping_version=mapping.mapping_version,
                normalization_version=NORMALIZATION_VERSION,
            )
            normalized_fact_id, _ = repository.get_or_create_normalized_fact(normalized_write)
            normalized_fact_count += 1

            reported.append(
                _ReportedNormalization(
                    raw=fact,
                    snapshot_id=snapshot.snapshot_id,
                    mapping=mapping,
                    period=period,
                    period_id=period_id,
                    normalized_fact_id=normalized_fact_id,
                    normalized_value=unit,
                )
            )

        derived_count, derived_period_ids, derived_warnings = _derive_cumulative_quarters(
            reported,
            snapshot.research_as_of_time,
            repository,
        )
        normalized_fact_count += derived_count
        period_ids.update(derived_period_ids)
        warnings.extend(derived_warnings)

        if normalized_fact_count:
            status = QualityStatus.PARTIAL if warnings else QualityStatus.PASS
            return FinancialNormalizationResult(
                snapshot_id=snapshot_id,
                status=status,
                normalized_fact_count=normalized_fact_count,
                period_count=len(period_ids),
                warnings=tuple(warnings),
            )
        return FinancialNormalizationResult(
            snapshot_id=snapshot_id,
            status=QualityStatus.BLOCKED,
            normalized_fact_count=0,
            period_count=0,
            warnings=tuple(warnings) or ("NO_APPROVED_FINANCIAL_FACT_MAPPINGS",),
        )


def _build_period(
    fact: RawFinancialFactForNormalization,
    fact_nature: FactNature,
    accounting_standard: str,
) -> FinancialPeriod:
    period_type = _period_type(fact, fact_nature)
    period_end = fact.instant_date if period_type is PeriodType.INSTANT else fact.period_end
    if period_end is None:
        raise PeriodSemanticsError("period_end or instant_date is required")
    if fact.form_type is None:
        raise PeriodSemanticsError("source form type is required")
    return FinancialPeriod.create(
        fiscal_year=fact.fiscal_year,
        fiscal_quarter=fact.fiscal_quarter,
        fiscal_period=fact.fiscal_period,
        period_type=period_type,
        fact_nature=fact_nature,
        period_start=fact.period_start,
        period_end=period_end,
        filing_date=fact.filed_at.date() if fact.filed_at is not None else None,
        published_at=fact.source_published_at,
        is_cumulative=fact.is_cumulative,
        is_single_quarter=(period_type is PeriodType.QUARTER and not fact.is_cumulative),
        accounting_standard=accounting_standard,
        source_form_type=fact.form_type,
    )


def _period_type(
    fact: RawFinancialFactForNormalization,
    fact_nature: FactNature,
) -> PeriodType:
    if fact_nature is FactNature.INSTANT:
        return PeriodType.INSTANT
    value = fact.fiscal_period.upper()
    if value in {"FY", "ANNUAL"} or fact.is_annual:
        return PeriodType.ANNUAL
    if value in {"H1", "HY", "HALF_YEAR"}:
        return PeriodType.HALF_YEAR
    if value in {"9M", "Q3_YTD", "NINE_MONTH_YTD"}:
        return PeriodType.NINE_MONTH_YTD
    if value in {"YTD", "YEAR_TO_DATE"}:
        return PeriodType.YEAR_TO_DATE
    if fact.fiscal_quarter is not None or value in {"Q1", "Q2", "Q3", "Q4"}:
        return PeriodType.QUARTER
    raise PeriodSemanticsError(f"unsupported fiscal period: {fact.fiscal_period}")


def _derive_cumulative_quarters(
    reported: list[_ReportedNormalization],
    research_as_of_time: datetime,
    repository: FinancialNormalizationRepository,
) -> tuple[int, set[UUID], list[str]]:
    groups: dict[tuple[UUID, str, int, str | None, str], list[_ReportedNormalization]] = {}
    for item in reported:
        mapping = item.mapping
        if mapping.fact_nature is not FactNature.DURATION or not item.raw.is_cumulative:
            continue
        try:
            concept = CanonicalConcept(mapping.canonical_concept_code)
        except ValueError:
            continue
        key = (
            item.raw.security_id,
            concept.value,
            item.raw.fiscal_year,
            item.raw.currency_code,
            mapping.accounting_standard,
        )
        groups.setdefault(key, []).append(item)

    count = 0
    period_ids: set[UUID] = set()
    warnings: list[str] = []
    for items in groups.values():
        ordered = sorted(items, key=lambda item: item.period.period_end)
        previous: _ReportedNormalization | None = None
        for current in ordered:
            mapping = current.mapping
            unit = current.normalized_value
            try:
                concept = CanonicalConcept(mapping.canonical_concept_code)
                current_value = FinancialValue(
                    fact_id=current.normalized_fact_id,
                    security_id=current.raw.security_id,
                    concept=concept,
                    period=current.period,
                    value=unit.normalized_value,
                    normalized_unit=unit.normalized_unit,
                    currency_code=current.raw.currency_code,
                    accounting_basis=mapping.accounting_standard,
                    source_published_at=current.raw.source_published_at,
                )
                previous_value = None
                if previous is not None:
                    previous_mapping = previous.mapping
                    previous_unit = previous.normalized_value
                    previous_value = FinancialValue(
                        fact_id=previous.normalized_fact_id,
                        security_id=previous.raw.security_id,
                        concept=concept,
                        period=previous.period,
                        value=previous_unit.normalized_value,
                        normalized_unit=previous_unit.normalized_unit,
                        currency_code=previous.raw.currency_code,
                        accounting_basis=previous_mapping.accounting_standard,
                        source_published_at=previous.raw.source_published_at,
                    )
                derived = deaccumulate_quarter(
                    current_value,
                    previous_value,
                    research_as_of_time=research_as_of_time,
                )
            except CalculationBlocked as error:
                warnings.append(
                    f"DEACCUMULATION_BLOCKED:{mapping.canonical_concept_code}:"
                    f"{current.raw.fiscal_year}:{error}"
                )
                previous = current
                continue

            quarter = current.raw.fiscal_quarter or 4
            start = (
                current.period.period_start
                if previous is None
                else previous.period.period_end + timedelta(days=1)
            )
            if start is None:
                warnings.append(f"DEACCUMULATION_BLOCKED:{current.raw.id}:MISSING_START")
                previous = current
                continue
            derived_period = FinancialPeriod.create(
                fiscal_year=current.raw.fiscal_year,
                fiscal_quarter=quarter,
                fiscal_period=f"Q{quarter}",
                period_type=PeriodType.QUARTER,
                fact_nature=FactNature.DURATION,
                period_start=start,
                period_end=current.period.period_end,
                filing_date=current.period.filing_date,
                published_at=current.period.published_at,
                is_cumulative=False,
                is_single_quarter=True,
                accounting_standard=mapping.accounting_standard,
                source_form_type=current.period.source_form_type,
            )
            period_id = repository.get_or_create_financial_period(
                FinancialPeriodWrite(
                    security_id=current.raw.security_id,
                    snapshot_id=current.snapshot_id,
                    fiscal_year=derived_period.fiscal_year,
                    fiscal_quarter=derived_period.fiscal_quarter,
                    fiscal_period=derived_period.fiscal_period,
                    period_type=derived_period.period_type.value,
                    period_start=derived_period.period_start,
                    period_end=derived_period.period_end,
                    filing_date=derived_period.filing_date,
                    published_at=derived_period.published_at,
                    duration_days=derived_period.duration_days,
                    is_annual=False,
                    is_cumulative=False,
                    is_single_quarter=True,
                    is_ttm=False,
                    accounting_standard=derived_period.accounting_standard,
                    source_form_type=derived_period.source_form_type,
                )
            )
            period_ids.add(period_id)
            assert current.raw.source_published_at is not None
            derived_fact_id, _ = repository.get_or_create_normalized_fact(
                NormalizedFinancialFactWrite(
                    security_id=current.raw.security_id,
                    snapshot_id=current.snapshot_id,
                    financial_period_id=period_id,
                    canonical_concept_id=mapping.canonical_concept_id,
                    source_financial_fact_id=current.raw.id,
                    mapping_id=mapping.mapping_id,
                    original_value=unit.original_value,
                    normalized_value=derived.value,
                    original_unit=unit.original_unit.value,
                    normalized_unit=derived.normalized_unit,
                    currency_code=derived.currency_code,
                    scale_factor=unit.scale_factor,
                    fact_nature=FactNature.DURATION,
                    is_reported=False,
                    is_derived_from_cumulative=True,
                    is_restated=current.raw.is_restated,
                    source_published_at=current.raw.source_published_at,
                    mapping_version=mapping.mapping_version,
                    normalization_version=NORMALIZATION_VERSION,
                )
            )
            for ordinal, input_id in enumerate(derived.input_fact_ids):
                role = (
                    "CURRENT_CUMULATIVE"
                    if input_id == current.normalized_fact_id
                    else "PREVIOUS_CUMULATIVE"
                )
                repository.get_or_create_normalized_fact_input(
                    NormalizedFactInputWrite(
                        normalized_fact_id=derived_fact_id,
                        input_normalized_fact_id=input_id,
                        input_role=role,
                        input_ordinal=ordinal,
                    )
                )
            warnings.extend(derived.warnings)
            count += 1
            previous = current
    return count, period_ids, warnings
