"""Immutable, source-neutral evidence ingestion manifests."""

from __future__ import annotations

import hashlib
import json
import re
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from stock_research_agent.domain.live_evidence.enums import (
    EvidenceSourceType,
    ManualLicenseStatus,
    ManualReviewDecision,
    ManualValidationStatus,
    RightsDecision,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
    SemanticVersion,
)

_STABLE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


class EvidenceRightsSnapshot(FrozenProviderContract):
    license_status: ManualLicenseStatus
    raw_storage_right: RightsDecision
    excerpt_right: RightsDecision
    derived_use_right: RightsDecision
    long_term_retention_right: RightsDecision


class EvidenceIngestionManifestWrite(FrozenProviderContract):
    source_type: EvidenceSourceType
    source_record_id: UUID
    security_id: UUID
    issuer_id: UUID
    raw_payload_id: UUID
    raw_payload_checksum: Checksum
    document_identity: str = Field(min_length=1, max_length=512)
    document_type: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    source_published_at: AwareUtcDateTime | None
    retrieved_at: AwareUtcDateTime
    rights: EvidenceRightsSnapshot
    validation_status: ManualValidationStatus
    validation_record_ids: tuple[UUID, ...] = Field(min_length=1, max_length=64)
    review_decision: ManualReviewDecision
    review_record_id: UUID
    synthetic_status: ProviderSyntheticStatus
    warning_codes: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("document_identity")
    @classmethod
    def validate_document_identity(cls, value: str) -> str:
        if value != value.strip() or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise ValueError("document_identity must be normalized printable text")
        return value

    @field_validator("validation_record_ids")
    @classmethod
    def validate_validation_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("validation_record_ids must be unique and sorted")
        return value

    @field_validator("warning_codes")
    @classmethod
    def validate_warning_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))) or any(
            _STABLE_CODE.fullmatch(item) is None for item in value
        ):
            raise ValueError("warning_codes must be unique sorted stable codes")
        return value

    @model_validator(mode="after")
    def validate_publication_time(self) -> EvidenceIngestionManifestWrite:
        if self.source_published_at is not None and self.source_published_at > self.retrieved_at:
            raise ValueError("source_published_at must not follow retrieved_at")
        return self


class EvidenceIngestionManifestRecord(EvidenceIngestionManifestWrite):
    id: UUID
    manifest_checksum: Checksum
    registry_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    registry_version: SemanticVersion
    registry_checksum: Checksum
    registry_signature: Checksum
    created_at: AwareUtcDateTime


_RECORD_ONLY_FIELDS = {
    "id",
    "manifest_checksum",
    "registry_id",
    "registry_version",
    "registry_checksum",
    "registry_signature",
    "created_at",
}


def _normalized_write(
    value: EvidenceIngestionManifestWrite | EvidenceIngestionManifestRecord,
) -> EvidenceIngestionManifestWrite:
    payload = value.model_dump(exclude=_RECORD_ONLY_FIELDS)
    validation_ids = tuple(sorted(payload.get("validation_record_ids", ()), key=str))
    warning_codes = tuple(sorted(payload.get("warning_codes", ())))
    if len(validation_ids) != len(set(validation_ids)) or len(warning_codes) != len(
        set(warning_codes)
    ):
        raise LiveEvidenceValidationError("MANIFEST_NONCANONICAL")
    payload["validation_record_ids"] = validation_ids
    payload["warning_codes"] = warning_codes
    try:
        return EvidenceIngestionManifestWrite.model_validate(payload)
    except ValueError as exc:
        raise LiveEvidenceValidationError("MANIFEST_NONCANONICAL") from exc


def canonical_manifest(
    value: EvidenceIngestionManifestWrite | EvidenceIngestionManifestRecord,
) -> str:
    """Return stable UTF-8 JSON, excluding generated registry record fields."""
    normalized = _normalized_write(value)
    return json.dumps(
        normalized.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def manifest_checksum(
    value: EvidenceIngestionManifestWrite | EvidenceIngestionManifestRecord,
) -> str:
    return hashlib.sha256(canonical_manifest(value).encode("utf-8")).hexdigest()


def verify_manifest_checksum(
    value: EvidenceIngestionManifestWrite | EvidenceIngestionManifestRecord,
    expected_checksum: Checksum,
) -> None:
    if manifest_checksum(value) != expected_checksum:
        raise LiveEvidenceValidationError("MANIFEST_CHECKSUM_MISMATCH")


class EvidenceManifestRegistry:
    def __init__(
        self,
        *,
        registry_id: str,
        registry_version: str,
        registry_checksum: str,
    ) -> None:
        if _STABLE_CODE.fullmatch(registry_id) is None:
            raise ValueError("registry_id must be a stable code")
        if re.fullmatch(r"\d+\.\d+\.\d+", registry_version) is None:
            raise ValueError("registry_version must be semantic")
        if re.fullmatch(r"[0-9a-f]{64}", registry_checksum) is None:
            raise ValueError("registry_checksum must be sha256")
        self.registry_id = registry_id
        self.registry_version = registry_version
        self.registry_checksum = registry_checksum

    def create(
        self,
        value: EvidenceIngestionManifestWrite,
        *,
        created_at: AwareUtcDateTime,
    ) -> EvidenceIngestionManifestRecord:
        if value.validation_status in {
            ManualValidationStatus.BLOCKED,
            ManualValidationStatus.FAIL,
        } or value.review_decision in {
            ManualReviewDecision.BLOCKED,
            ManualReviewDecision.REJECTED,
        }:
            raise LiveEvidenceValidationError("MANIFEST_UPSTREAM_INVALID")
        rights = value.rights
        if rights.license_status is not ManualLicenseStatus.CONFIRMED or any(
            decision is not RightsDecision.ALLOWED
            for decision in (
                rights.raw_storage_right,
                rights.excerpt_right,
                rights.derived_use_right,
                rights.long_term_retention_right,
            )
        ):
            raise LiveEvidenceValidationError("MANIFEST_LICENSE_BLOCKED")

        checksum = manifest_checksum(value)
        signature = self._signature(checksum)
        return EvidenceIngestionManifestRecord(
            **value.model_dump(),
            id=uuid4(),
            manifest_checksum=checksum,
            registry_id=self.registry_id,
            registry_version=self.registry_version,
            registry_checksum=self.registry_checksum,
            registry_signature=signature,
            created_at=created_at,
        )

    def verify(self, value: EvidenceIngestionManifestRecord) -> bool:
        checksum = manifest_checksum(value)
        return (
            value.registry_id == self.registry_id
            and value.registry_version == self.registry_version
            and value.registry_checksum == self.registry_checksum
            and value.manifest_checksum == checksum
            and value.registry_signature == self._signature(checksum)
        )

    def _signature(self, manifest_checksum: str) -> str:
        material = ":".join(
            (
                self.registry_id,
                self.registry_version,
                self.registry_checksum,
                manifest_checksum,
            )
        )
        return hashlib.sha256(material.encode("ascii")).hexdigest()
