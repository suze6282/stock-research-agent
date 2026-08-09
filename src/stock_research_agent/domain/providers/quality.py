"""Deterministic Provider batch quality contracts."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.providers.artifacts import (
    ProviderBatch,
    ProviderDeadLetterWrite,
    ProviderRecord,
    ProviderRecordStatus,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.errors import (
    ProviderFailure,
    safe_provider_error,
)
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)


class ProviderQualityRule(StrEnum):
    IDENTITY = "IDENTITY"
    TEMPORAL = "TEMPORAL"
    SOURCE_CHECKSUM = "SOURCE_CHECKSUM"
    SYNTHETIC_ISOLATION = "SYNTHETIC_ISOLATION"
    DUPLICATE = "DUPLICATE"
    DECIMAL = "DECIMAL"
    CURRENCY_UNIT = "CURRENCY_UNIT"
    MISSING = "MISSING"


class ProviderQualityContext(FrozenProviderContract):
    research_as_of_time: AwareUtcDateTime
    provider_definition_id: UUID
    provider_capability_id: UUID
    raw_artifact_id: UUID
    source_checksum: Checksum
    synthetic_status: ProviderSyntheticStatus
    allowed_currencies: tuple[str, ...] = Field(max_length=64)
    allowed_units: tuple[str, ...] = Field(max_length=64)


class ProviderQualityIssue(FrozenProviderContract):
    rule: ProviderQualityRule
    record_key: str = Field(min_length=1, max_length=256)
    safe_detail: str = Field(min_length=1, max_length=256)


class ProviderQualityResult(FrozenProviderContract):
    passed: bool
    issues: tuple[ProviderQualityIssue, ...] = Field(max_length=10_000)


class ProviderDataQualityValidator:
    """Validate persisted projections without repairing or mutating input records."""

    def validate(
        self,
        batch: ProviderBatch,
        context: ProviderQualityContext,
    ) -> ProviderQualityResult:
        issues: list[ProviderQualityIssue] = []
        seen: set[str] = set()
        for record in batch.records:
            identity_checksum = record.identity.checksum
            if identity_checksum in seen:
                issues.append(_issue(ProviderQualityRule.DUPLICATE, record))
            seen.add(identity_checksum)
            if (
                record.identity.provider_definition_id != context.provider_definition_id
                or record.identity.provider_capability_id != context.provider_capability_id
                or record.raw_artifact_id != context.raw_artifact_id
            ):
                issues.append(_issue(ProviderQualityRule.IDENTITY, record))
            if (
                record.source_published_at is not None
                and record.source_published_at > context.research_as_of_time
            ):
                issues.append(_issue(ProviderQualityRule.TEMPORAL, record))
            if record.source_checksum != context.source_checksum:
                issues.append(_issue(ProviderQualityRule.SOURCE_CHECKSUM, record))
            if record.synthetic_status is not context.synthetic_status:
                issues.append(_issue(ProviderQualityRule.SYNTHETIC_ISOLATION, record))
            if not _valid_decimals(record):
                issues.append(_issue(ProviderQualityRule.DECIMAL, record))
            if not _valid_currency_unit(record, context):
                issues.append(_issue(ProviderQualityRule.CURRENCY_UNIT, record))
            if record.status is ProviderRecordStatus.MISSING and any(
                value is not None for value in record.numeric_values.values()
            ):
                issues.append(_issue(ProviderQualityRule.MISSING, record))
        ordered = tuple(
            sorted(
                issues,
                key=lambda item: (item.record_key, item.rule.value),
            )
        )
        return ProviderQualityResult(passed=not ordered, issues=ordered)


def _valid_decimals(record: ProviderRecord) -> bool:
    for value in record.numeric_values.values():
        if value is None:
            continue
        try:
            number = Decimal(value)
        except (InvalidOperation, ValueError):
            return False
        if not number.is_finite():
            return False
    return True


def _valid_currency_unit(
    record: ProviderRecord,
    context: ProviderQualityContext,
) -> bool:
    currency = record.text_values.get("currency")
    unit = record.text_values.get("unit")
    return (currency is None or currency in context.allowed_currencies) and (
        unit is None or unit in context.allowed_units
    )


def _issue(rule: ProviderQualityRule, record: ProviderRecord) -> ProviderQualityIssue:
    return ProviderQualityIssue(
        rule=rule,
        record_key=record.identity.record_key,
        safe_detail=f"{rule.value} validation failed",
    )


class DeadLetterContext(FrozenProviderContract):
    sync_run_id: UUID
    manifest_id: UUID
    retention_permitted: bool


class DeadLetterService:
    """Create safe append-only diagnostics; replay remains an explicit control action."""

    def __init__(
        self,
        repair_audit: Callable[[UUID, str], None] | None = None,
    ) -> None:
        self._repair_audit = repair_audit

    def reject(
        self,
        record: ProviderRecord,
        failure: ProviderFailure,
        context: DeadLetterContext,
    ) -> ProviderDeadLetterWrite:
        if not context.retention_permitted:
            raise PermissionError("DEAD_LETTER_RETENTION_BLOCKED")
        return ProviderDeadLetterWrite(
            sync_run_id=context.sync_run_id,
            manifest_id=context.manifest_id,
            source_identity=record.identity.source_identity,
            safe_error_code=failure.code.value,
            safe_detail=failure.safe_message,
        )

    def reject_exception(
        self,
        record: ProviderRecord,
        exc: Exception,
        context: DeadLetterContext,
    ) -> ProviderDeadLetterWrite:
        return self.reject(record, safe_provider_error(exc), context)

    def repair(self, item_id: UUID, *, authorized: bool) -> None:
        if not authorized:
            raise PermissionError("EXPLICIT_REPAIR_AUTHORIZATION_REQUIRED")
        if self._repair_audit is None:
            raise RuntimeError("DEAD_LETTER_REPAIR_AUDIT_REQUIRED")
        self._repair_audit(item_id, "DEAD_LETTER_REPAIR_AUTHORIZED")
