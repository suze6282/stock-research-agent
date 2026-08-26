from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

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
from stock_research_agent.domain.live_evidence.manifests import (
    EvidenceIngestionManifestWrite,
    EvidenceManifestRegistry,
    EvidenceRightsSnapshot,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _rights(**changes: object) -> EvidenceRightsSnapshot:
    values: dict[str, object] = {
        "license_status": ManualLicenseStatus.CONFIRMED,
        "raw_storage_right": RightsDecision.ALLOWED,
        "excerpt_right": RightsDecision.ALLOWED,
        "derived_use_right": RightsDecision.ALLOWED,
        "long_term_retention_right": RightsDecision.ALLOWED,
    }
    values.update(changes)
    return EvidenceRightsSnapshot.model_validate(values)


def _write(**changes: object) -> EvidenceIngestionManifestWrite:
    values: dict[str, object] = {
        "source_type": EvidenceSourceType.MANUAL_IMPORT,
        "source_record_id": uuid4(),
        "security_id": uuid4(),
        "issuer_id": uuid4(),
        "raw_payload_id": uuid4(),
        "raw_payload_checksum": "a" * 64,
        "document_identity": "issuer-filing-2025",
        "document_type": "ANNUAL_REPORT",
        "source_published_at": NOW,
        "retrieved_at": NOW,
        "rights": _rights(),
        "validation_status": ManualValidationStatus.PASS,
        "validation_record_ids": (uuid4(),),
        "review_decision": ManualReviewDecision.APPROVED,
        "review_record_id": uuid4(),
        "synthetic_status": ProviderSyntheticStatus.REAL_VERIFIED,
        "warning_codes": (),
    }
    values.update(changes)
    return EvidenceIngestionManifestWrite.model_validate(values)


def _registry() -> EvidenceManifestRegistry:
    return EvidenceManifestRegistry(
        registry_id="EVIDENCE_MANIFEST_REGISTRY",
        registry_version="1.0.0",
        registry_checksum="f" * 64,
    )


@pytest.mark.parametrize("source_type", list(EvidenceSourceType))
def test_registry_creates_source_neutral_immutable_manifest(
    source_type: EvidenceSourceType,
) -> None:
    record = _registry().create(_write(source_type=source_type), created_at=NOW)

    assert record.source_type is source_type
    assert isinstance(record.id, UUID)
    assert _registry().verify(record)
    with pytest.raises(ValidationError):
        record.__setattr__("security_id", uuid4())


@pytest.mark.parametrize(
    "changes",
    [
        {"validation_status": ManualValidationStatus.BLOCKED},
        {"validation_status": ManualValidationStatus.FAIL},
        {"review_decision": ManualReviewDecision.REJECTED},
        {"review_decision": ManualReviewDecision.BLOCKED},
    ],
)
def test_manifest_rejects_invalid_upstream_evidence(changes: dict[str, object]) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        _registry().create(_write(**changes), created_at=NOW)

    assert exc_info.value.code == "MANIFEST_UPSTREAM_INVALID"


@pytest.mark.parametrize(
    "rights",
    [
        _rights(license_status=ManualLicenseStatus.UNKNOWN),
        _rights(raw_storage_right=RightsDecision.PROHIBITED),
        _rights(excerpt_right=RightsDecision.UNKNOWN),
        _rights(derived_use_right=RightsDecision.PROHIBITED),
        _rights(long_term_retention_right=RightsDecision.UNKNOWN),
    ],
)
def test_manifest_rejects_blocked_or_unknown_rights(
    rights: EvidenceRightsSnapshot,
) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        _registry().create(_write(rights=rights), created_at=NOW)

    assert exc_info.value.code == "MANIFEST_LICENSE_BLOCKED"


def test_registry_signature_detects_manifest_tampering() -> None:
    registry = _registry()
    record = registry.create(_write(), created_at=NOW)
    tampered = record.model_copy(update={"raw_payload_checksum": "b" * 64})

    assert not registry.verify(tampered)
