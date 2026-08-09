"""Stable schemas shared by financial normalization services and repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from stock_research_agent.domain.financials.enums import (
    FactNature,
    QualityStatus,
    UnitType,
)


@dataclass(frozen=True, slots=True)
class SnapshotForNormalization:
    """The immutable snapshot boundary used by financial normalization."""

    snapshot_id: UUID
    security_id: UUID
    research_as_of_time: datetime
    status: str


@dataclass(frozen=True, slots=True)
class RawFinancialFactForNormalization:
    """A provider fact preserved exactly as captured inside a snapshot."""

    id: UUID
    security_id: UUID
    provider_id: UUID
    provider_code: str
    statement_type: str
    provider_concept: str
    taxonomy: str | None
    context_id: str | None
    dimensions: tuple[tuple[str, str], ...]
    value: Decimal
    unit: str
    currency_code: str | None
    fiscal_year: int
    fiscal_quarter: int | None
    fiscal_period: str
    period_start: date | None
    period_end: date | None
    instant_date: date | None
    filed_at: datetime | None
    source_published_at: datetime | None
    form_type: str | None
    is_annual: bool
    is_cumulative: bool
    is_restated: bool
    retrieved_at: datetime


@dataclass(frozen=True, slots=True)
class ApprovedFactMapping:
    """An exact, approved provider-to-canonical concept mapping."""

    mapping_id: UUID
    canonical_concept_id: UUID
    canonical_concept_code: str
    fact_nature: FactNature
    default_unit_type: UnitType
    accounting_standard: str
    mapping_version: str


@dataclass(frozen=True, slots=True)
class FinancialPeriodWrite:
    """Validated fiscal period ready for idempotent persistence."""

    security_id: UUID
    snapshot_id: UUID
    fiscal_year: int
    fiscal_quarter: int | None
    fiscal_period: str
    period_type: str
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


@dataclass(frozen=True, slots=True)
class NormalizedFinancialFactWrite:
    """A reported normalized fact with source and rule lineage."""

    security_id: UUID
    snapshot_id: UUID
    financial_period_id: UUID
    canonical_concept_id: UUID
    source_financial_fact_id: UUID
    mapping_id: UUID
    original_value: Decimal
    normalized_value: Decimal
    original_unit: str
    normalized_unit: str
    currency_code: str | None
    scale_factor: Decimal
    fact_nature: FactNature
    is_reported: bool
    is_derived_from_cumulative: bool
    is_restated: bool
    source_published_at: datetime
    mapping_version: str
    normalization_version: str


@dataclass(frozen=True, slots=True)
class NormalizedFactInputWrite:
    """One immutable input edge for a derived normalized fact."""

    normalized_fact_id: UUID
    input_normalized_fact_id: UUID
    input_role: str
    input_ordinal: int


@dataclass(frozen=True, slots=True)
class FinancialNormalizationResult:
    """Outcome of a deterministic snapshot normalization attempt."""

    snapshot_id: UUID
    status: QualityStatus
    normalized_fact_count: int
    period_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CalculationSnapshot:
    snapshot_id: UUID
    security_id: UUID
    research_as_of_time: datetime
    status: str


@dataclass(frozen=True, slots=True)
class NormalizedFactForCalculation:
    id: UUID
    canonical_concept_code: str
    financial_period_id: UUID
    fiscal_year: int
    fiscal_quarter: int | None
    fiscal_period: str
    period_type: str
    period_start: date | None
    period_end: date
    duration_days: int | None
    accounting_standard: str
    is_cumulative: bool
    is_single_quarter: bool
    normalized_value: Decimal
    normalized_unit: str
    currency_code: str | None
    source_published_at: datetime


@dataclass(frozen=True, slots=True)
class CalculationRunWrite:
    security_id: UUID
    snapshot_id: UUID
    status: str
    calculation_version: str
    formula_set_version: str
    mapping_version: str
    normalization_version: str
    input_checksum: str
    started_at: datetime
    warning_count: int


@dataclass(frozen=True, slots=True)
class CalculationRunRecord:
    id: UUID
    security_id: UUID
    snapshot_id: UUID
    status: QualityStatus
    input_checksum: str
    metric_count: int
    warning_count: int


@dataclass(frozen=True, slots=True)
class DerivedMetricWrite:
    calculation_run_id: UUID
    security_id: UUID
    snapshot_id: UUID
    formula_definition_id: UUID
    metric_code: str
    metric_period: str
    period_end: date | None
    value: Decimal | None
    value_state: str
    unit: str
    currency_code: str | None
    quality_status: QualityStatus
    formula_version: str
    warning_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CalculationInputWrite:
    calculation_run_id: UUID
    metric_code: str
    normalized_fact_id: UUID | None
    source_record_type: str | None
    source_record_id: UUID | None
    input_role: str
    value_used: Decimal
    unit: str
    currency_code: str | None


@dataclass(frozen=True, slots=True)
class CalculationResult:
    calculation_run_id: UUID
    snapshot_id: UUID
    status: QualityStatus
    metric_count: int
    warning_count: int
    input_checksum: str


@dataclass(frozen=True, slots=True)
class FinancialPeriodRecord:
    id: UUID
    security_id: UUID
    snapshot_id: UUID
    fiscal_year: int
    fiscal_quarter: int | None
    fiscal_period: str
    period_type: str
    period_start: date | None
    period_end: date
    published_at: datetime | None
    duration_days: int | None
    is_annual: bool
    is_cumulative: bool
    is_single_quarter: bool
    is_ttm: bool
    accounting_standard: str
    source_form_type: str


@dataclass(frozen=True, slots=True)
class NormalizedFinancialFactRecord:
    id: UUID
    security_id: UUID
    snapshot_id: UUID
    financial_period_id: UUID
    canonical_concept_code: str
    source_financial_fact_id: UUID
    original_value: Decimal
    normalized_value: Decimal
    original_unit: str
    normalized_unit: str
    currency_code: str | None
    is_reported: bool
    is_derived_from_cumulative: bool
    is_restated: bool
    source_published_at: datetime | None
    mapping_version: str
    normalization_version: str


@dataclass(frozen=True, slots=True)
class DerivedMetricRecord:
    id: UUID
    calculation_run_id: UUID
    security_id: UUID
    snapshot_id: UUID
    metric_code: str
    metric_period: str
    period_end: date | None
    value: Decimal | None
    value_state: str
    unit: str
    currency_code: str | None
    quality_status: QualityStatus
    formula_version: str
    warning_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CalculationInputRecord:
    id: UUID
    calculation_run_id: UUID
    metric_code: str
    normalized_fact_id: UUID | None
    source_record_type: str | None
    source_record_id: UUID | None
    input_role: str
    value_used: Decimal
    unit: str
    currency_code: str | None


@dataclass(frozen=True, slots=True)
class CalculationRunDetail:
    id: UUID
    security_id: UUID
    snapshot_id: UUID
    status: QualityStatus
    calculation_version: str
    formula_set_version: str
    mapping_version: str
    normalization_version: str
    input_checksum: str
    started_at: datetime | None
    completed_at: datetime | None
    warning_count: int
    error_code: str | None
    safe_error_message: str | None
