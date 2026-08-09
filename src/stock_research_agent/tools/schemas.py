"""Strict safe contracts for the internal read-only tool boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    PlainSerializer,
    field_validator,
    model_validator,
)

from stock_research_agent.domain.data_access.enums import DataCategory, QualityStatus

JsonDecimal = Annotated[
    Decimal,
    PlainSerializer(lambda value: str(value), return_type=str, when_used="json"),
]
ToolStatus = Literal["PASS", "PARTIAL", "BLOCKED", "FAIL"]
EvidenceOrigin = Literal["FIXTURE", "LIVE", "MIXED", "UNKNOWN"]
EvidenceAccessMode = Literal["OFFLINE", "ONLINE", "MIXED", "UNKNOWN"]
EvidenceLiveStatus = Literal["NOT_LIVE", "LIVE", "MIXED", "UNKNOWN"]


class ToolModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class SnapshotOrAsOfInput(ToolModel):
    security_id: UUID
    snapshot_id: UUID | None = None
    research_as_of_time: datetime | None = None

    @field_validator("research_as_of_time")
    @classmethod
    def normalize_research_as_of(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("research_as_of_time must be timezone aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_exact_scope(self) -> Self:
        if (self.snapshot_id is None) == (self.research_as_of_time is None):
            raise ValueError("exactly one snapshot or as-of scope is required")
        return self


class GetLatestCloseInput(SnapshotOrAsOfInput):
    local_trading_date: date | None = None


class GetDailyPriceHistoryInput(SnapshotOrAsOfInput):
    date_from: date | None = None
    local_trading_date: date | None = None
    limit: int = Field(default=100, ge=1, le=100)

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if (
            self.date_from is not None
            and self.local_trading_date is not None
            and self.date_from > self.local_trading_date
        ):
            raise ValueError("date_from cannot follow local_trading_date")
        return self


class GetCorporateActionsInput(SnapshotOrAsOfInput):
    limit: int = Field(default=100, ge=1, le=100)


class GetReportedFinancialFactsInput(SnapshotOrAsOfInput):
    limit: int = Field(default=100, ge=1, le=100)


class ListSourceDocumentsInput(SnapshotOrAsOfInput):
    limit: int = Field(default=100, ge=1, le=100)


class GetSourceDocumentMetadataInput(SnapshotOrAsOfInput):
    document_id: UUID


class GetDataSnapshotInput(ToolModel):
    snapshot_id: UUID


class ListSnapshotItemsInput(ToolModel):
    snapshot_id: UUID
    limit: int = Field(default=100, ge=1, le=100)


class SnapshotFinancialInput(ToolModel):
    security_id: UUID
    snapshot_id: UUID
    limit: int = Field(default=100, ge=1, le=100)


class GetNormalizedFinancialFactsInput(SnapshotFinancialInput):
    concept_code: str | None = Field(default=None, min_length=2, max_length=64)


class GetFinancialPeriodsInput(SnapshotFinancialInput):
    period_type: str | None = Field(default=None, min_length=2, max_length=32)


class GetFinancialMetricsInput(SnapshotFinancialInput):
    metric_code: str | None = Field(default=None, min_length=2, max_length=64)


class GetMetricDetailInput(ToolModel):
    security_id: UUID
    snapshot_id: UUID
    metric_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")


class GetMetricLineageInput(ToolModel):
    calculation_run_id: UUID
    metric_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")


class GetCalculationRunInput(ToolModel):
    calculation_run_id: UUID


class ToolQuality(ToolModel):
    status: QualityStatus
    record_count: int = Field(ge=0, le=100)


class ToolProvenance(ToolModel):
    data_origin: EvidenceOrigin
    access_mode: EvidenceAccessMode
    live_status: EvidenceLiveStatus


class ToolEnvelope[RecordT](ToolModel):
    tool_name: str
    tool_version: str
    status: ToolStatus
    data: tuple[RecordT, ...] = ()
    source_record_ids: tuple[UUID, ...] = ()
    provider_ids: tuple[UUID, ...] = ()
    snapshot_id: UUID | None = None
    research_as_of_time: datetime | None = None
    retrieved_at: datetime | None = None
    warnings: tuple[str, ...] = ()
    quality: ToolQuality
    provenance: ToolProvenance

    @field_validator("research_as_of_time", "retrieved_at")
    @classmethod
    def normalize_optional_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("tool envelope timestamps must be timezone aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_envelope_shape(self) -> Self:
        if len(self.data) != self.quality.record_count:
            raise ValueError("quality record count must match data")
        if self.status != self.quality.status:
            raise ValueError("quality status must match envelope status")
        if self.snapshot_id is not None and self.research_as_of_time is not None:
            raise ValueError("tool envelope cannot contain both point-in-time scopes")
        return self


class DailyPriceData(ToolModel):
    id: UUID
    security_id: UUID
    provider_id: UUID
    provider_symbol: str
    trading_date: date
    market_timestamp: datetime | None
    open: JsonDecimal | None
    high: JsonDecimal | None
    low: JsonDecimal | None
    close: JsonDecimal | None
    volume: int | None
    currency_code: str
    adjustment_type: str | None
    provider_adjusted_close: JsonDecimal | None
    source_published_at: datetime | None
    retrieved_at: datetime


class CorporateActionData(ToolModel):
    id: UUID
    security_id: UUID
    provider_id: UUID
    provider_action_id: str | None
    action_type: str
    announcement_date: date | None
    ex_date: date | None
    record_date: date | None
    payment_date: date | None
    cash_amount: JsonDecimal | None
    currency_code: str | None
    ratio_numerator: JsonDecimal | None
    ratio_denominator: JsonDecimal | None
    status: str
    source_published_at: datetime | None
    retrieved_at: datetime


class ReportedFinancialFactData(ToolModel):
    id: UUID
    security_id: UUID
    provider_id: UUID
    document_id: UUID | None
    statement_type: str
    provider_concept: str
    reported_label: str | None
    taxonomy: str | None
    context_id: str | None
    dimensions: dict[str, JsonValue]
    value: JsonDecimal | None
    unit: str | None
    currency_code: str | None
    fiscal_year: int | None
    fiscal_quarter: int | None
    fiscal_period: str | None
    period_start: date | None
    period_end: date | None
    instant_date: date | None
    filed_at: datetime | None
    source_published_at: datetime | None
    form_type: str | None
    is_annual: bool | None
    is_cumulative: bool | None
    is_audited: bool | None
    is_restated: bool | None
    provider_record_id: str | None
    retrieved_at: datetime


class SourceDocumentMetadataData(ToolModel):
    id: UUID
    security_id: UUID
    provider_id: UUID
    provider_document_id: str | None
    document_type: str
    title: str
    form_type: str | None
    accession_number: str | None
    announcement_id: str | None
    period_end: date | None
    filed_at: datetime | None
    published_at: datetime | None
    source_url: str
    primary_document_name: str | None
    mime_type: str | None
    checksum: str | None
    byte_size: int | None
    document_status: str
    retrieved_at: datetime


class DataSnapshotData(ToolModel):
    id: UUID
    security_id: UUID
    research_as_of_time: datetime
    snapshot_version: int
    status: str
    completed_at: datetime | None
    checksum: str | None
    formula_version: str
    created_at: datetime


class SnapshotItemData(ToolModel):
    id: UUID
    snapshot_id: UUID
    provider_id: UUID
    category: DataCategory
    source_record_type: str
    source_record_id: UUID
    source_published_at: datetime | None
    retrieved_at: datetime
    checksum: str
    created_at: datetime


class FinancialPeriodData(ToolModel):
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


class NormalizedFinancialFactData(ToolModel):
    id: UUID
    security_id: UUID
    snapshot_id: UUID
    financial_period_id: UUID
    canonical_concept_code: str
    source_financial_fact_id: UUID
    original_value: JsonDecimal
    normalized_value: JsonDecimal
    original_unit: str
    normalized_unit: str
    currency_code: str | None
    is_reported: bool
    is_derived_from_cumulative: bool
    is_restated: bool
    source_published_at: datetime | None
    mapping_version: str
    normalization_version: str


class FinancialMetricData(ToolModel):
    id: UUID
    calculation_run_id: UUID
    security_id: UUID
    snapshot_id: UUID
    metric_code: str
    metric_period: str
    period_end: date | None
    value: JsonDecimal | None
    value_state: str
    unit: str
    currency_code: str | None
    quality_status: str
    formula_version: str
    warning_codes: tuple[str, ...]


class MetricLineageData(ToolModel):
    id: UUID
    calculation_run_id: UUID
    metric_code: str
    normalized_fact_id: UUID | None
    source_record_type: str | None
    source_record_id: UUID | None
    input_role: str
    value_used: JsonDecimal
    unit: str
    currency_code: str | None


class CalculationRunData(ToolModel):
    id: UUID
    security_id: UUID
    snapshot_id: UUID
    status: str
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


class FinancialToolEnvelope[RecordT](ToolEnvelope[RecordT]):
    calculation_run_id: UUID | None = None
    formula_version: str | None = None


class LatestCloseEnvelope(ToolEnvelope[DailyPriceData]):
    pass


class DailyPriceHistoryEnvelope(ToolEnvelope[DailyPriceData]):
    pass


class CorporateActionsEnvelope(ToolEnvelope[CorporateActionData]):
    pass


class ReportedFinancialFactsEnvelope(ToolEnvelope[ReportedFinancialFactData]):
    pass


class SourceDocumentsEnvelope(ToolEnvelope[SourceDocumentMetadataData]):
    pass


class SourceDocumentMetadataEnvelope(ToolEnvelope[SourceDocumentMetadataData]):
    pass


class DataSnapshotEnvelope(ToolEnvelope[DataSnapshotData]):
    pass


class SnapshotItemsEnvelope(ToolEnvelope[SnapshotItemData]):
    pass


class FinancialPeriodsEnvelope(FinancialToolEnvelope[FinancialPeriodData]):
    pass


class NormalizedFinancialFactsEnvelope(FinancialToolEnvelope[NormalizedFinancialFactData]):
    pass


class FinancialMetricsEnvelope(FinancialToolEnvelope[FinancialMetricData]):
    pass


class MetricDetailEnvelope(FinancialToolEnvelope[FinancialMetricData]):
    pass


class MetricLineageEnvelope(FinancialToolEnvelope[MetricLineageData]):
    pass


class CalculationRunEnvelope(FinancialToolEnvelope[CalculationRunData]):
    pass


__all__ = [
    "CorporateActionData",
    "CorporateActionsEnvelope",
    "DailyPriceData",
    "DailyPriceHistoryEnvelope",
    "DataSnapshotData",
    "DataSnapshotEnvelope",
    "GetCorporateActionsInput",
    "GetCalculationRunInput",
    "GetDailyPriceHistoryInput",
    "GetDataSnapshotInput",
    "GetLatestCloseInput",
    "GetFinancialMetricsInput",
    "GetFinancialPeriodsInput",
    "GetMetricDetailInput",
    "GetMetricLineageInput",
    "GetNormalizedFinancialFactsInput",
    "GetReportedFinancialFactsInput",
    "GetSourceDocumentMetadataInput",
    "LatestCloseEnvelope",
    "CalculationRunEnvelope",
    "FinancialMetricsEnvelope",
    "FinancialPeriodsEnvelope",
    "ListSnapshotItemsInput",
    "ListSourceDocumentsInput",
    "ReportedFinancialFactData",
    "ReportedFinancialFactsEnvelope",
    "MetricDetailEnvelope",
    "MetricLineageEnvelope",
    "NormalizedFinancialFactsEnvelope",
    "SnapshotItemData",
    "SnapshotItemsEnvelope",
    "SourceDocumentMetadataData",
    "SourceDocumentMetadataEnvelope",
    "SourceDocumentsEnvelope",
    "ToolEnvelope",
    "ToolModel",
    "ToolProvenance",
    "ToolQuality",
]
