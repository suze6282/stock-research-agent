from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from stock_research_agent.domain.documents.enums import (
    CitationStatus,
    DocumentLanguage,
    SourceVersionStatus,
    TrustLevel,
)
from stock_research_agent.domain.documents.schemas import (
    CitationVerification,
    DocumentVersionRecord,
)
from stock_research_agent.domain.live_evidence.citation_eligibility import (
    EvidenceCitationRequest,
    evaluate_citation_eligibility,
)
from stock_research_agent.domain.live_evidence.enums import (
    EvidenceSourceType,
    ManualLicenseStatus,
    ManualReviewDecision,
    ManualValidationStatus,
    RightsDecision,
)
from stock_research_agent.domain.live_evidence.manifests import (
    EvidenceIngestionManifestRecord,
    EvidenceIngestionManifestWrite,
    EvidenceManifestRegistry,
    EvidenceRightsSnapshot,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
SECURITY_ID = UUID("11111111-1111-4111-8111-111111111111")
PAYLOAD_ID = UUID("22222222-2222-4222-8222-222222222222")
CHECKSUM = "a" * 64


def _registry() -> EvidenceManifestRegistry:
    return EvidenceManifestRegistry(
        registry_id="EVIDENCE_MANIFEST_REGISTRY",
        registry_version="1.0.0",
        registry_checksum="f" * 64,
    )


def _manifest() -> EvidenceIngestionManifestRecord:
    return _registry().create(
        EvidenceIngestionManifestWrite(
            source_type=EvidenceSourceType.MANUAL_IMPORT,
            source_record_id=uuid4(),
            security_id=SECURITY_ID,
            issuer_id=uuid4(),
            raw_payload_id=PAYLOAD_ID,
            raw_payload_checksum=CHECKSUM,
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
            validation_record_ids=(uuid4(),),
            review_decision=ManualReviewDecision.APPROVED,
            review_record_id=uuid4(),
            synthetic_status=ProviderSyntheticStatus.REAL_VERIFIED,
            warning_codes=(),
        ),
        created_at=NOW,
    )


def _version(**changes: object) -> DocumentVersionRecord:
    values: dict[str, object] = {
        "id": uuid4(),
        "logical_document_id": uuid4(),
        "source_document_id": uuid4(),
        "security_id": SECURITY_ID,
        "provider_id": uuid4(),
        "source_payload_id": PAYLOAD_ID,
        "version_number": 1,
        "supersedes_document_version_id": None,
        "storage_uri": "blob://memory/0123456789abcdef0123456789abcdef",
        "mime_type": "text/html",
        "checksum_algorithm": "sha256",
        "checksum": CHECKSUM,
        "byte_size": 128,
        "published_at": NOW,
        "filed_at": NOW,
        "period_end": None,
        "retrieved_at": NOW,
        "document_language": DocumentLanguage.EN_US,
        "trust_level": TrustLevel.UNKNOWN,
        "evidence_origin": "SOURCE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
        "source_version_status": SourceVersionStatus.ACTIVE,
        "created_at": NOW,
    }
    values.update(changes)
    return DocumentVersionRecord.model_validate(values)


def _request(
    *,
    manifest: EvidenceIngestionManifestRecord | None = None,
    version: DocumentVersionRecord | None = None,
    citation_document_version_id: UUID | None = None,
    verification_status: CitationStatus = CitationStatus.VALID,
) -> EvidenceCitationRequest:
    document = version or _version()
    citation_id = uuid4()
    return EvidenceCitationRequest(
        manifest=manifest or _manifest(),
        manifest_registry=_registry(),
        document_version=document,
        citation_id=citation_id,
        citation_document_version_id=citation_document_version_id or document.id,
        verification=CitationVerification(
            status=verification_status,
            citation_id=citation_id,
        ),
        research_as_of_time=NOW,
    )


def test_valid_verified_citation_is_eligible() -> None:
    decision = evaluate_citation_eligibility(_request())

    assert decision.status == "ELIGIBLE"
    assert decision.warning_codes == ()


@pytest.mark.parametrize(
    "case",
    [
        _request(verification_status=CitationStatus.INVALID),
        _request(citation_document_version_id=uuid4()),
        _request(version=_version(checksum="b" * 64)),
    ],
)
def test_unverified_or_mismatched_document_is_blocked(
    case: EvidenceCitationRequest,
) -> None:
    decision = evaluate_citation_eligibility(case)

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("CITATION_DOCUMENT_UNVERIFIED",)


def test_unapproved_manifest_source_is_blocked() -> None:
    manifest = _manifest().model_copy(update={"registry_signature": "0" * 64})
    decision = evaluate_citation_eligibility(_request(manifest=manifest))

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("CITATION_SOURCE_BLOCKED",)


def test_future_document_is_blocked() -> None:
    request = _request(version=_version(published_at=NOW + timedelta(seconds=1)))
    request = replace(request, research_as_of_time=NOW)

    decision = evaluate_citation_eligibility(request)

    assert decision.status == "BLOCKED"
    assert decision.warning_codes == ("CITATION_FUTURE_DATA",)
