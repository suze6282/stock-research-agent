from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

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
    canonical_manifest,
    manifest_checksum,
    verify_manifest_checksum,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
FIRST_ID = UUID("00000000-0000-0000-0000-000000000001")
SECOND_ID = UUID("00000000-0000-0000-0000-000000000002")


def _write() -> EvidenceIngestionManifestWrite:
    return EvidenceIngestionManifestWrite(
        source_type=EvidenceSourceType.OFFLINE_FIXTURE,
        source_record_id=UUID("00000000-0000-0000-0000-000000000003"),
        security_id=UUID("00000000-0000-0000-0000-000000000004"),
        issuer_id=UUID("00000000-0000-0000-0000-000000000005"),
        raw_payload_id=UUID("00000000-0000-0000-0000-000000000006"),
        raw_payload_checksum="a" * 64,
        document_identity="stable-document",
        document_type="ANNUAL_REPORT",
        source_published_at=NOW,
        retrieved_at=NOW,
        rights=EvidenceRightsSnapshot(
            license_status=ManualLicenseStatus.CONFIRMED,
            raw_storage_right=RightsDecision.ALLOWED,
            excerpt_right=RightsDecision.ALLOWED,
            derived_use_right=RightsDecision.ALLOWED,
            long_term_retention_right=RightsDecision.ALLOWED,
        ),
        validation_status=ManualValidationStatus.PASS,
        validation_record_ids=(FIRST_ID, SECOND_ID),
        review_decision=ManualReviewDecision.APPROVED,
        review_record_id=UUID("00000000-0000-0000-0000-000000000007"),
        synthetic_status=ProviderSyntheticStatus.FIXTURE_REAL_EXCERPT,
        warning_codes=("FIRST_WARNING", "SECOND_WARNING"),
    )


def test_manifest_canonicalization_sorts_set_like_fields() -> None:
    write = _write()
    reordered = write.model_copy(
        update={
            "validation_record_ids": (SECOND_ID, FIRST_ID),
            "warning_codes": ("SECOND_WARNING", "FIRST_WARNING"),
        }
    )

    assert canonical_manifest(reordered) == canonical_manifest(write)
    assert manifest_checksum(reordered) == manifest_checksum(write)


def test_generated_record_fields_do_not_change_manifest_checksum() -> None:
    write = _write()
    record = EvidenceManifestRegistry(
        registry_id="EVIDENCE_MANIFEST_REGISTRY",
        registry_version="1.0.0",
        registry_checksum="f" * 64,
    ).create(write, created_at=NOW)

    assert canonical_manifest(record) == canonical_manifest(write)
    assert manifest_checksum(record) == manifest_checksum(write)


def test_manifest_checksum_mismatch_has_stable_failure_code() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        verify_manifest_checksum(_write(), "b" * 64)

    assert exc_info.value.code == "MANIFEST_CHECKSUM_MISMATCH"


def test_noncanonical_manifest_reason_is_rejected() -> None:
    invalid = _write().model_copy(update={"warning_codes": ("not stable",)})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        canonical_manifest(invalid)

    assert exc_info.value.code == "MANIFEST_NONCANONICAL"
