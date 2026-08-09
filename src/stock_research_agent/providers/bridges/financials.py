"""Bridge Provider-reported raw facts into Stage 5 normalization inputs."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol, cast
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.data_access.schemas import ProviderFinancialFactWrite
from stock_research_agent.domain.providers.artifacts import (
    ProviderBatch,
    ProviderIngestionManifestRecord,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)

StatementValue = Literal[
    "BALANCE_SHEET",
    "INCOME_STATEMENT",
    "CASH_FLOW",
    "EQUITY",
    "COMPREHENSIVE_INCOME",
    "OTHER",
]
_FORBIDDEN_DERIVED_FIELDS = frozenset(
    {
        "canonical_formula_code",
        "derived_metric_code",
        "formula_version",
        "normalized_concept",
        "ttm_value",
    }
)


class FinancialFactBridgeContext(FrozenProviderContract):
    security_id: UUID
    provider_id: UUID
    source_payload_id: UUID
    source_payload_checksum: Checksum
    retrieved_at: AwareUtcDateTime
    research_as_of_time: AwareUtcDateTime
    derived_use_approved: bool
    raw_fact_retention_approved: bool


class FinancialFactBridgeResult(FrozenProviderContract):
    staged_fact_count: int = Field(ge=0)
    manifest_id: UUID
    manifest_checksum: Checksum
    raw_artifact_id: UUID
    source_payload_id: UUID
    normalization_run_created: Literal[False] = False
    calculation_run_created: Literal[False] = False


class FinancialFactBridgeRepository(Protocol):
    def add_financial_fact(self, value: ProviderFinancialFactWrite) -> object: ...


class FinancialFactProviderBridge:
    """Append raw Provider facts without normalizing or calculating them."""

    def __init__(self, repository: FinancialFactBridgeRepository) -> None:
        self._repository = repository

    def stage(
        self,
        manifest: ProviderIngestionManifestRecord,
        batch: ProviderBatch,
        context: FinancialFactBridgeContext,
    ) -> FinancialFactBridgeResult:
        if not context.derived_use_approved or not context.raw_fact_retention_approved:
            raise ValueError("FINANCIAL_FACT_DERIVED_STORAGE_NOT_APPROVED")
        if context.retrieved_at > context.research_as_of_time:
            raise ValueError("FINANCIAL_FACT_FUTURE_DATA")
        if manifest.manifest_checksum != batch.manifest_checksum:
            raise ValueError("FINANCIAL_FACT_MANIFEST_MISMATCH")
        if manifest.record_count != batch.record_count:
            raise ValueError("FINANCIAL_FACT_RECORD_COUNT_MISMATCH")
        if manifest.synthetic_status in {
            ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
            ProviderSyntheticStatus.UNKNOWN,
        }:
            raise ValueError("SYNTHETIC_FINANCIAL_FACT_WRITE_FORBIDDEN")
        staged: list[ProviderFinancialFactWrite] = []
        for record in batch.records:
            if record.raw_artifact_id != manifest.raw_artifact_id:
                raise ValueError("FINANCIAL_FACT_RAW_ARTIFACT_MISMATCH")
            if record.source_checksum != context.source_payload_checksum:
                raise ValueError("FINANCIAL_FACT_RAW_CHECKSUM_MISMATCH")
            if record.synthetic_status is not manifest.synthetic_status:
                raise ValueError("FINANCIAL_FACT_SYNTHETIC_STATUS_MISMATCH")
            if record.source_published_at is not None and (
                record.source_published_at > context.research_as_of_time
            ):
                raise ValueError("FINANCIAL_FACT_FUTURE_DATA")
            values = record.text_values
            if any(values.get(field) is not None for field in _FORBIDDEN_DERIVED_FIELDS):
                raise ValueError("PROVIDER_FORMULA_SUBSTITUTION_FORBIDDEN")
            if values.get("security_id") != str(context.security_id):
                raise ValueError("FINANCIAL_FACT_SECURITY_MISMATCH")
            filed_at = _datetime_value(values.get("filed_at"))
            if filed_at is not None and filed_at > context.research_as_of_time:
                raise ValueError("FINANCIAL_FACT_FUTURE_DATA")
            staged.append(
                ProviderFinancialFactWrite(
                    security_id=context.security_id,
                    provider_id=context.provider_id,
                    source_payload_id=context.source_payload_id,
                    document_id=_optional_uuid(values.get("document_id")),
                    statement_type=_statement(values.get("statement_type")),
                    provider_concept=_required(values.get("provider_concept"), "CONCEPT"),
                    reported_label=values.get("reported_label"),
                    taxonomy=values.get("taxonomy"),
                    context_id=values.get("context_id"),
                    dimensions={},
                    value=_decimal_value(record.numeric_values.get("value")),
                    unit=values.get("unit"),
                    currency_code=values.get("currency_code"),
                    fiscal_year=_optional_int(values.get("fiscal_year")),
                    fiscal_quarter=_optional_int(values.get("fiscal_quarter")),
                    fiscal_period=values.get("fiscal_period"),
                    period_start=_date_value(values.get("period_start")),
                    period_end=_date_value(values.get("period_end")),
                    instant_date=_date_value(values.get("instant_date")),
                    filed_at=filed_at,
                    source_published_at=record.source_published_at,
                    form_type=values.get("form_type"),
                    is_annual=_boolean_value(values.get("is_annual")),
                    is_cumulative=_boolean_value(values.get("is_cumulative")),
                    is_audited=_boolean_value(values.get("is_audited")),
                    is_restated=_boolean_value(values.get("is_restated")),
                    provider_record_id=values.get("provider_record_id"),
                    retrieved_at=context.retrieved_at,
                )
            )
        if manifest.batch_checksum != batch.batch_checksum:
            raise ValueError("FINANCIAL_FACT_BATCH_CHECKSUM_MISMATCH")
        for value in staged:
            self._repository.add_financial_fact(value)
        return FinancialFactBridgeResult(
            staged_fact_count=len(staged),
            manifest_id=manifest.id,
            manifest_checksum=manifest.manifest_checksum,
            raw_artifact_id=manifest.raw_artifact_id,
            source_payload_id=context.source_payload_id,
            normalization_run_created=False,
            calculation_run_created=False,
        )


def _decimal_value(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (bool, float)) or not isinstance(value, str):
        raise ValueError("FINANCIAL_FACT_DECIMAL_INVALID")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError("FINANCIAL_FACT_DECIMAL_INVALID") from None
    if not result.is_finite():
        raise ValueError("FINANCIAL_FACT_DECIMAL_INVALID")
    return result


def _required(value: str | None, field: str) -> str:
    if value is None or not value or value != value.strip():
        raise ValueError(f"FINANCIAL_FACT_{field}_MISSING")
    return value


def _statement(value: str | None) -> StatementValue:
    allowed = {
        "BALANCE_SHEET",
        "INCOME_STATEMENT",
        "CASH_FLOW",
        "EQUITY",
        "COMPREHENSIVE_INCOME",
        "OTHER",
    }
    if value not in allowed:
        raise ValueError("FINANCIAL_FACT_STATEMENT_TYPE_INVALID")
    return cast(StatementValue, value)


def _date_value(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("FINANCIAL_FACT_DATE_INVALID") from None


def _datetime_value(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("FINANCIAL_FACT_TIMESTAMP_INVALID") from None


def _optional_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        raise ValueError("FINANCIAL_FACT_DOCUMENT_ID_INVALID") from None


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    if not value.isascii() or not value.isdigit():
        raise ValueError("FINANCIAL_FACT_INTEGER_INVALID")
    return int(value)


def _boolean_value(value: str | None) -> bool | None:
    if value is None:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError("FINANCIAL_FACT_BOOLEAN_INVALID")


__all__ = [
    "FinancialFactBridgeContext",
    "FinancialFactBridgeRepository",
    "FinancialFactBridgeResult",
    "FinancialFactProviderBridge",
]
