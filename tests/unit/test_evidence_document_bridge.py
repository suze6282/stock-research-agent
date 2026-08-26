from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from stock_research_agent.domain.documents.enums import (
    DocumentLanguage,
    SourceVersionStatus,
    TrustLevel,
)
from stock_research_agent.domain.documents.schemas import (
    DocumentVersionResult,
    RegisterDocumentVersionRequest,
    SourceBodyRecord,
)
from stock_research_agent.domain.live_evidence.document_bridge import (
    ArtifactDocumentAdmissionRequest,
    admit_document,
)
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
    EvidenceIngestionManifestRecord,
    EvidenceIngestionManifestWrite,
    EvidenceManifestRegistry,
    EvidenceRightsSnapshot,
)
from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
SECURITY_ID = UUID("11111111-1111-4111-8111-111111111111")
ISSUER_ID = UUID("22222222-2222-4222-8222-222222222222")
PAYLOAD_ID = UUID("33333333-3333-4333-8333-333333333333")
CHECKSUM = "a" * 64


class _Registrar:
    def __init__(self) -> None:
        self.requests: list[RegisterDocumentVersionRequest] = []

    def register(self, request: RegisterDocumentVersionRequest) -> DocumentVersionResult:
        self.requests.append(request)
        return DocumentVersionResult(status="BLOCKED", version=None, warnings=("TEST_REGISTRAR",))


def _registry() -> EvidenceManifestRegistry:
    return EvidenceManifestRegistry(
        registry_id="EVIDENCE_MANIFEST_REGISTRY",
        registry_version="1.0.0",
        registry_checksum="f" * 64,
    )


def _manifest() -> EvidenceIngestionManifestRecord:
    write = EvidenceIngestionManifestWrite(
        source_type=EvidenceSourceType.MANUAL_IMPORT,
        source_record_id=uuid4(),
        security_id=SECURITY_ID,
        issuer_id=ISSUER_ID,
        raw_payload_id=PAYLOAD_ID,
        raw_payload_checksum=CHECKSUM,
        document_identity="issuer-filing-2025",
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
    )
    return _registry().create(write, created_at=NOW)


def _registration(**body_changes: object) -> RegisterDocumentVersionRequest:
    body_values: dict[str, object] = {
        "source_document_id": uuid4(),
        "security_id": SECURITY_ID,
        "provider_id": uuid4(),
        "source_payload_id": PAYLOAD_ID,
        "document_status": "AVAILABLE",
        "storage_uri": "blob://memory/0123456789abcdef0123456789abcdef",
        "checksum": CHECKSUM,
        "byte_size": 128,
        "mime_type": "text/html",
        "published_at": NOW,
        "filed_at": NOW,
        "period_end": None,
        "retrieved_at": NOW,
    }
    body_values.update(body_changes)
    return RegisterDocumentVersionRequest(
        logical_document_id=uuid4(),
        source_body=SourceBodyRecord.model_validate(body_values),
        document_language=DocumentLanguage.EN_US,
        trust_level=TrustLevel.UNKNOWN,
        evidence_origin="SOURCE",
        access_mode="OFFLINE",
        live_status="NOT_LIVE",
        source_version_status=SourceVersionStatus.ACTIVE,
    )


def _request(
    *,
    manifest: EvidenceIngestionManifestRecord | None = None,
    registration: RegisterDocumentVersionRequest | None = None,
    registrar: _Registrar | None = None,
) -> ArtifactDocumentAdmissionRequest:
    return ArtifactDocumentAdmissionRequest(
        manifest=manifest or _manifest(),
        manifest_registry=_registry(),
        expected_security_id=SECURITY_ID,
        expected_issuer_id=ISSUER_ID,
        expected_document_identity="issuer-filing-2025",
        registration=registration or _registration(),
        registrar=registrar or _Registrar(),
    )


def test_approved_manifest_is_admitted_through_existing_document_service() -> None:
    registrar = _Registrar()
    request = _request(registrar=registrar)

    result = admit_document(request)

    assert result.warnings == ("TEST_REGISTRAR",)
    assert registrar.requests == [request.registration]


@pytest.mark.parametrize(
    "registration",
    [
        _registration(source_payload_id=uuid4()),
        _registration(checksum="b" * 64),
    ],
)
def test_artifact_mismatch_is_rejected(
    registration: RegisterDocumentVersionRequest,
) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        admit_document(_request(registration=registration))

    assert exc_info.value.code == "DOCUMENT_ARTIFACT_MISMATCH"


def test_unverified_manifest_is_rejected_before_document_service() -> None:
    manifest = _manifest().model_copy(update={"registry_signature": "0" * 64})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        admit_document(_request(manifest=manifest))

    assert exc_info.value.code == "DOCUMENT_SOURCE_NOT_APPROVED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_security_id", uuid4()),
        ("expected_issuer_id", uuid4()),
        ("expected_document_identity", "different-document"),
    ],
)
def test_document_identity_scope_mismatch_is_rejected(
    field: str,
    value: object,
) -> None:
    request = _request()
    mismatched = replace(request, **{field: value})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        admit_document(mismatched)

    assert exc_info.value.code == "DOCUMENT_IDENTITY_MISMATCH"
