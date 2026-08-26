"""Admission bridge from governed raw evidence to immutable document versions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from stock_research_agent.domain.documents.schemas import (
    DocumentVersionRecord,
    DocumentVersionResult,
    RegisterDocumentVersionRequest,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.gate_b_pilot import (
    CommittedSecSettlement,
    SecDocumentCitationResult,
    ValidatedSecSettlement,
)
from stock_research_agent.domain.live_evidence.manifests import (
    EvidenceIngestionManifestRecord,
    EvidenceManifestRegistry,
)
from stock_research_agent.domain.providers.artifacts import ProviderBatch


class DocumentRegistrar(Protocol):
    def register(self, request: RegisterDocumentVersionRequest) -> DocumentVersionResult: ...


@dataclass(frozen=True, slots=True)
class ArtifactDocumentAdmissionRequest:
    manifest: EvidenceIngestionManifestRecord
    manifest_registry: EvidenceManifestRegistry
    expected_security_id: UUID
    expected_issuer_id: UUID
    expected_document_identity: str
    registration: RegisterDocumentVersionRequest
    registrar: DocumentRegistrar


def admit_document(
    request: ArtifactDocumentAdmissionRequest,
) -> DocumentVersionResult:
    """Delegate approved bytes to the existing immutable DocumentVersion service."""
    manifest = request.manifest
    if not request.manifest_registry.verify(manifest):
        raise LiveEvidenceValidationError("DOCUMENT_SOURCE_NOT_APPROVED")
    if (
        manifest.security_id != request.expected_security_id
        or manifest.issuer_id != request.expected_issuer_id
        or manifest.document_identity != request.expected_document_identity
    ):
        raise LiveEvidenceValidationError("DOCUMENT_IDENTITY_MISMATCH")

    body = request.registration.source_body
    if body.security_id != manifest.security_id:
        raise LiveEvidenceValidationError("DOCUMENT_IDENTITY_MISMATCH")
    if (
        body.source_payload_id != manifest.raw_payload_id
        or body.checksum != manifest.raw_payload_checksum
        or body.published_at != manifest.source_published_at
        or body.retrieved_at != manifest.retrieved_at
    ):
        raise LiveEvidenceValidationError("DOCUMENT_ARTIFACT_MISMATCH")

    return request.registrar.register(request.registration)


class ProviderArtifactDocumentRequestFactory(Protocol):
    def build(
        self,
        committed: CommittedSecSettlement,
        validated: ValidatedSecSettlement,
    ) -> ArtifactDocumentAdmissionRequest: ...


class ProviderArtifactCitationPublisher(Protocol):
    def add_citations(
        self,
        version: DocumentVersionRecord,
        batch: ProviderBatch,
    ) -> tuple[UUID, ...]: ...


class ProviderArtifactDocumentBridge:
    """Bridge only committed provider lineage into existing document/citation services."""

    def __init__(
        self,
        *,
        request_factory: ProviderArtifactDocumentRequestFactory,
        citation_publisher: ProviderArtifactCitationPublisher,
    ) -> None:
        self._request_factory = request_factory
        self._citation_publisher = citation_publisher

    def admit(
        self,
        committed: CommittedSecSettlement,
        validated: ValidatedSecSettlement,
    ) -> SecDocumentCitationResult:
        if (
            committed.artifact_id != validated.artifact_id
            or committed.request_attempt_id != validated.request_attempt_id
            or committed.content_checksum != validated.source_checksum
        ):
            raise LiveEvidenceValidationError("DOCUMENT_ARTIFACT_MISMATCH")
        request = self._request_factory.build(committed, validated)
        body = request.registration.source_body
        if (
            body.security_id != validated.context.security_id
            or body.checksum != committed.content_checksum
            or body.storage_uri != committed.storage_uri
            or body.retrieved_at != validated.context.retrieved_at
        ):
            raise LiveEvidenceValidationError("DOCUMENT_ARTIFACT_MISMATCH")
        result = admit_document(request)
        if result.status == "BLOCKED" or result.version is None:
            raise LiveEvidenceValidationError("DOCUMENT_VERSION_BLOCKED")
        citation_ids = self._citation_publisher.add_citations(result.version, validated.batch)
        if not citation_ids:
            raise LiveEvidenceValidationError("CITATION_REQUIRED")
        return SecDocumentCitationResult(
            document_version_id=result.version.id,
            citation_ids=citation_ids,
        )
