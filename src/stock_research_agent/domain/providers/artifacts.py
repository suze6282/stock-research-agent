from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
    SemanticVersion,
)


class ProviderIssueSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ProviderIssueStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    ACCEPTED = "ACCEPTED"


class ProviderDeadLetterStatus(StrEnum):
    OPEN = "OPEN"
    REPAIRED = "REPAIRED"
    DISMISSED = "DISMISSED"


class ProviderRawArtifactDraft(FrozenProviderContract):
    content_type: str = Field(min_length=1, max_length=128)
    expected_checksum: Checksum | None = None
    store_raw_permitted: bool

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        if (
            value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
            or "/" not in value
            or ".." in value
            or "\\" in value
        ):
            raise ValueError("content_type is invalid")
        return value


class ProviderRawArtifactWrite(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    sync_run_id: UUID
    request_attempt_id: UUID
    license_policy_id: UUID
    source_identity: str = Field(min_length=1, max_length=512)
    source_checksum: Checksum
    byte_count: int = Field(gt=0, le=52_428_800)
    content_type: str = Field(min_length=1, max_length=128)
    blob_key: str = Field(min_length=1, max_length=512)
    acquired_at: AwareUtcDateTime
    source_published_at: AwareUtcDateTime | None = None
    synthetic_status: ProviderSyntheticStatus

    @field_validator("blob_key")
    @classmethod
    def validate_blob_key(cls, value: str) -> str:
        if (
            value.startswith(("/", "\\"))
            or "\\" in value
            or ".." in value.split("/")
            or (len(value) >= 2 and value[1] == ":")
        ):
            raise ValueError("blob_key must be a safe relative storage key")
        return value


class ProviderRawArtifactRecord(ProviderRawArtifactWrite):
    id: UUID
    created_at: AwareUtcDateTime


class ProviderRawArtifactReservation(FrozenProviderContract):
    id: UUID
    value: ProviderRawArtifactWrite


class ProviderIngestionManifestWrite(FrozenProviderContract):
    raw_artifact_id: UUID
    sync_run_id: UUID
    adapter_version: SemanticVersion
    parser_version: SemanticVersion
    schema_version: str = Field(min_length=1, max_length=64)
    batch_checksum: Checksum
    record_count: int = Field(ge=0)
    source_published_at: AwareUtcDateTime | None = None
    warning_codes: tuple[str, ...] = Field(default=(), max_length=64)
    synthetic_status: ProviderSyntheticStatus
    manifest_checksum: Checksum


class ProviderIngestionManifestRecord(ProviderIngestionManifestWrite):
    id: UUID
    created_at: AwareUtcDateTime


class ProviderManifestBatch(FrozenProviderContract):
    record_identities: tuple[str, ...] = Field(min_length=1, max_length=10_000)
    batch_checksum: Checksum

    @field_validator("record_identities")
    @classmethod
    def validate_record_identities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(
            not identity
            or identity != identity.strip()
            or len(identity) > 256
            or any(ord(character) < 32 or ord(character) == 127 for character in identity)
            for identity in value
        ):
            raise ValueError("record identities must be bounded printable text")
        if value != tuple(sorted(set(value))):
            raise ValueError("record identities must be unique and stably ordered")
        return value


class ProviderIngestionContext(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    sync_run_id: UUID
    request_attempt_id: UUID
    security_id: UUID | None = None
    research_as_of_time: AwareUtcDateTime
    adapter_version: SemanticVersion
    parser_version: SemanticVersion
    schema_version: str = Field(min_length=1, max_length=64)
    synthetic_status: ProviderSyntheticStatus
    warning_codes: tuple[str, ...] = Field(default=(), max_length=64)


def build_ingestion_manifest(
    artifact: ProviderRawArtifactRecord,
    batch: ProviderManifestBatch,
    context: ProviderIngestionContext,
) -> ProviderIngestionManifestWrite:
    """Seal deterministic parsed-batch lineage without mutating the raw artifact."""

    artifact_lineage = (
        artifact.provider_definition_id,
        artifact.provider_capability_id,
        artifact.sync_run_id,
        artifact.request_attempt_id,
        artifact.synthetic_status,
    )
    context_lineage = (
        context.provider_definition_id,
        context.provider_capability_id,
        context.sync_run_id,
        context.request_attempt_id,
        context.synthetic_status,
    )
    if artifact_lineage != context_lineage:
        raise ValueError("PROVIDER_MANIFEST_LINEAGE_MISMATCH")
    if (
        artifact.source_published_at is not None
        and artifact.source_published_at > context.research_as_of_time
    ):
        raise ValueError("PROVIDER_MANIFEST_FUTURE_DATA")

    warnings = set(context.warning_codes)
    if artifact.source_published_at is None:
        warnings.add("UNKNOWN_PUBLISHED_AT")
    ordered_warnings = tuple(sorted(warnings))
    checksum_payload = {
        "provider_definition_id": artifact.provider_definition_id,
        "provider_capability_id": artifact.provider_capability_id,
        "sync_run_id": artifact.sync_run_id,
        "request_attempt_id": artifact.request_attempt_id,
        "security_id": context.security_id,
        "raw_artifact_id": artifact.id,
        "raw_source_checksum": artifact.source_checksum,
        "raw_retrieved_at": artifact.acquired_at,
        "source_published_at": artifact.source_published_at,
        "research_as_of_time": context.research_as_of_time,
        "adapter_version": context.adapter_version,
        "parser_version": context.parser_version,
        "schema_version": context.schema_version,
        "record_identities": batch.record_identities,
        "batch_checksum": batch.batch_checksum,
        "synthetic_status": context.synthetic_status,
        "warning_codes": ordered_warnings,
    }
    return ProviderIngestionManifestWrite(
        raw_artifact_id=artifact.id,
        sync_run_id=artifact.sync_run_id,
        adapter_version=context.adapter_version,
        parser_version=context.parser_version,
        schema_version=context.schema_version,
        batch_checksum=batch.batch_checksum,
        record_count=len(batch.record_identities),
        source_published_at=artifact.source_published_at,
        warning_codes=ordered_warnings,
        synthetic_status=context.synthetic_status,
        manifest_checksum=provider_checksum(checksum_payload),
    )


class ProviderRecordStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class ProviderRecordIdentity(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    source_identity: str = Field(min_length=1, max_length=512)
    record_key: str = Field(min_length=1, max_length=256)
    revision: int = Field(ge=1, le=1_000_000)

    @model_validator(mode="after")
    def validate_printable_identity(self) -> ProviderRecordIdentity:
        for value in (self.source_identity, self.record_key):
            if value != value.strip() or any(
                ord(character) < 32 or ord(character) == 127 for character in value
            ):
                raise ValueError("record identity must be normalized printable text")
        return self

    @property
    def checksum(self) -> str:
        return provider_checksum(self)


class ProviderRecord(FrozenProviderContract):
    identity: ProviderRecordIdentity
    raw_artifact_id: UUID
    source_checksum: Checksum
    source_published_at: AwareUtcDateTime | None
    status: ProviderRecordStatus
    numeric_values: dict[str, str | None]
    text_values: dict[str, str | None]
    warning_codes: tuple[str, ...] = Field(default=(), max_length=64)
    synthetic_status: ProviderSyntheticStatus

    @field_validator("numeric_values")
    @classmethod
    def validate_decimal_strings(
        cls,
        value: dict[str, str | None],
    ) -> dict[str, str | None]:
        for item in value.values():
            if item is None:
                continue
            try:
                number = Decimal(item)
            except (InvalidOperation, ValueError) as exc:
                raise ValueError("numeric values must be Decimal strings") from exc
            if not number.is_finite():
                raise ValueError("numeric values must be finite")
        return value

    @model_validator(mode="after")
    def validate_status_semantics(self) -> ProviderRecord:
        if self.status is ProviderRecordStatus.PARTIAL and not self.warning_codes:
            raise ValueError("PARTIAL records require a warning")
        if self.status is ProviderRecordStatus.MISSING:
            if not self.warning_codes:
                raise ValueError("MISSING records require a warning")
            if any(value is not None for value in self.numeric_values.values()):
                raise ValueError("missing numeric values cannot be filled with zero")
        return self


class ProviderBatch(FrozenProviderContract):
    manifest_checksum: Checksum
    records: tuple[ProviderRecord, ...] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def validate_stable_identity_order(self) -> ProviderBatch:
        keys = tuple(record.identity.record_key for record in self.records)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("batch record identities must be unique and stably ordered")
        identity_checksums = tuple(record.identity.checksum for record in self.records)
        if len(identity_checksums) != len(set(identity_checksums)):
            raise ValueError("batch contains duplicate record identity")
        return self

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def batch_checksum(self) -> str:
        return build_provider_batch_checksum(self.records)


def build_provider_batch_checksum(records: tuple[ProviderRecord, ...]) -> str:
    return provider_checksum(records)


class ProviderDataQualityIssueWrite(FrozenProviderContract):
    sync_run_id: UUID
    manifest_id: UUID
    rule_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    severity: ProviderIssueSeverity
    status: ProviderIssueStatus = ProviderIssueStatus.OPEN
    safe_detail: str = Field(min_length=1, max_length=1024)

    @field_validator("safe_detail")
    @classmethod
    def validate_safe_detail(cls, value: str) -> str:
        if value != value.strip() or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise ValueError("safe_detail must be normalized printable text")
        return value


class ProviderDataQualityIssueRecord(ProviderDataQualityIssueWrite):
    id: UUID
    created_at: AwareUtcDateTime


class ProviderDeadLetterWrite(FrozenProviderContract):
    sync_run_id: UUID
    manifest_id: UUID
    source_identity: str = Field(min_length=1, max_length=512)
    status: ProviderDeadLetterStatus = ProviderDeadLetterStatus.OPEN
    safe_error_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    safe_detail: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def validate_safe_text(self) -> ProviderDeadLetterWrite:
        for value in (self.source_identity, self.safe_detail):
            if value != value.strip() or any(
                ord(character) < 32 or ord(character) == 127 for character in value
            ):
                raise ValueError("dead-letter text must be normalized and printable")
        return self


class ProviderDeadLetterRecord(ProviderDeadLetterWrite):
    id: UUID
    created_at: AwareUtcDateTime
