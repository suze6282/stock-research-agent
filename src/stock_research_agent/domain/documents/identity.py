"""Deterministic registration of exact, immutable document bytes."""

from __future__ import annotations

from uuid import UUID

from stock_research_agent.domain.documents.repositories import DocumentVersionRepository
from stock_research_agent.domain.documents.schemas import (
    BindSnapshotDocumentVersionRequest,
    DocumentVersionRecord,
    DocumentVersionResult,
    DocumentVersionWrite,
    RegisterDocumentVersionRequest,
    SnapshotDocumentVersionResult,
    SnapshotDocumentVersionWrite,
    SourceBodyRecord,
)
from stock_research_agent.infrastructure.blob_storage import BlobStorage, BlobStorageError


class DocumentVersionService:
    def __init__(
        self,
        repository: DocumentVersionRepository,
        blob_storage: BlobStorage,
    ) -> None:
        self._repository = repository
        self._blob_storage = blob_storage

    def register(self, request: RegisterDocumentVersionRequest) -> DocumentVersionResult:
        logical_document_id = request.logical_document_id
        if logical_document_id is None:
            return DocumentVersionResult(
                status="BLOCKED",
                version=None,
                warnings=("STABLE_DOCUMENT_IDENTITY_REQUIRED",),
            )

        body = request.source_body
        persisted_body = self._repository.get_source_body(body.source_document_id)
        if persisted_body != body:
            return _blocked("SOURCE_BODY_RECORD_MISMATCH")
        logical_security_id = self._repository.get_logical_document_security_id(logical_document_id)
        if logical_security_id is None:
            return _blocked("LOGICAL_DOCUMENT_NOT_FOUND")
        if logical_security_id != body.security_id:
            return _blocked("LOGICAL_DOCUMENT_SECURITY_MISMATCH")

        existing = self._repository.find_version(logical_document_id, body.checksum)
        if existing is not None and not _same_content_metadata(existing, body):
            return _blocked("DOCUMENT_VERSION_METADATA_CONFLICT")
        if not self._blob_matches(body):
            return _blocked("SOURCE_BODY_BLOB_METADATA_MISMATCH")
        if existing is not None:
            if not _same_policy(existing, request):
                return _blocked("DOCUMENT_VERSION_POLICY_CONFLICT")
            return DocumentVersionResult(status="REUSED", version=existing)

        version_number = request.version_number or self._repository.next_version_number(
            logical_document_id
        )
        relation_error = self._validate_supersedes_relation(
            logical_document_id=logical_document_id,
            version_number=version_number,
            supersedes_document_version_id=request.supersedes_document_version_id,
        )
        if relation_error is not None:
            return _blocked(relation_error)
        write = DocumentVersionWrite(
            logical_document_id=logical_document_id,
            source_document_id=body.source_document_id,
            security_id=body.security_id,
            provider_id=body.provider_id,
            source_payload_id=body.source_payload_id,
            version_number=version_number,
            supersedes_document_version_id=request.supersedes_document_version_id,
            storage_uri=body.storage_uri,
            mime_type=body.mime_type,
            checksum_algorithm="sha256",
            checksum=body.checksum,
            byte_size=body.byte_size,
            published_at=body.published_at,
            filed_at=body.filed_at,
            period_end=body.period_end,
            retrieved_at=body.retrieved_at,
            document_language=request.document_language,
            trust_level=request.trust_level,
            evidence_origin=request.evidence_origin,
            access_mode=request.access_mode,
            live_status=request.live_status,
            source_version_status=request.source_version_status,
        )
        record, acquired = self._repository.acquire_version(write)
        if not _same_content_metadata(record, body):
            return _blocked("DOCUMENT_VERSION_METADATA_CONFLICT")
        if not _same_policy(record, request):
            return _blocked("DOCUMENT_VERSION_POLICY_CONFLICT")
        return DocumentVersionResult(
            status="CREATED" if acquired else "REUSED",
            version=record,
        )

    def _validate_supersedes_relation(
        self,
        *,
        logical_document_id: UUID,
        version_number: int,
        supersedes_document_version_id: UUID | None,
    ) -> str | None:
        if supersedes_document_version_id is None:
            return None
        superseded = self._repository.get_document_version(supersedes_document_version_id)
        if superseded is None:
            return "SUPERSEDES_VERSION_NOT_FOUND"
        if superseded.logical_document_id != logical_document_id:
            return "SUPERSEDES_VERSION_LOGICAL_DOCUMENT_MISMATCH"
        if superseded.version_number >= version_number:
            return "SUPERSEDES_VERSION_ORDER_INVALID"
        return None

    def _blob_matches(self, body: SourceBodyRecord) -> bool:
        try:
            metadata = self._blob_storage.metadata(body.storage_uri)
            content = self._blob_storage.get(body.storage_uri)
        except BlobStorageError:
            return False
        return (
            metadata.checksum_sha256 == body.checksum
            and metadata.size_bytes == body.byte_size
            and metadata.content_type == body.mime_type
            and len(content) == body.byte_size
            and self._blob_storage.checksum(body.storage_uri) == body.checksum
        )


def _same_content_metadata(version: DocumentVersionRecord, body: SourceBodyRecord) -> bool:
    return (
        version.source_document_id == body.source_document_id
        and version.security_id == body.security_id
        and version.provider_id == body.provider_id
        and version.source_payload_id == body.source_payload_id
        and version.storage_uri == body.storage_uri
        and version.mime_type == body.mime_type
        and version.checksum == body.checksum
        and version.byte_size == body.byte_size
    )


def _same_policy(version: DocumentVersionRecord, request: RegisterDocumentVersionRequest) -> bool:
    return (
        version.supersedes_document_version_id == request.supersedes_document_version_id
        and version.published_at == request.source_body.published_at
        and version.filed_at == request.source_body.filed_at
        and version.period_end == request.source_body.period_end
        and version.retrieved_at == request.source_body.retrieved_at
        and version.document_language == request.document_language
        and version.trust_level == request.trust_level
        and version.evidence_origin == request.evidence_origin
        and version.access_mode == request.access_mode
        and version.live_status == request.live_status
        and version.source_version_status == request.source_version_status
    )


def _blocked(warning: str) -> DocumentVersionResult:
    return DocumentVersionResult(status="BLOCKED", version=None, warnings=(warning,))


def bind_version_to_snapshot(
    repository: DocumentVersionRepository,
    request: BindSnapshotDocumentVersionRequest,
) -> SnapshotDocumentVersionResult:
    version = repository.get_document_version(request.document_version_id)
    if version is None:
        return _blocked_link("DOCUMENT_VERSION_NOT_FOUND")
    evidence = repository.get_snapshot_body_evidence(request.snapshot_id, request.snapshot_item_id)
    if evidence is None:
        return _blocked_link("SNAPSHOT_ITEM_NOT_FOUND")
    if evidence.category != "SOURCE_DOCUMENTS" or evidence.source_record_type != "source_documents":
        return _blocked_link("SNAPSHOT_ITEM_IS_NOT_DOCUMENT_BODY")
    if (
        evidence.source_record_id != version.source_document_id
        or evidence.security_id != version.security_id
        or evidence.provider_id != version.provider_id
    ):
        return _blocked_link("SNAPSHOT_ITEM_DOCUMENT_VERSION_MISMATCH")
    existing = repository.find_snapshot_version_link(
        request.snapshot_id, request.document_version_id
    )
    if existing is not None:
        if existing.snapshot_item_id != request.snapshot_item_id:
            return _blocked_link("SNAPSHOT_DOCUMENT_LINK_CONFLICT")
        return SnapshotDocumentVersionResult(status="REUSED", link=existing)
    link = repository.add_snapshot_version_link(
        SnapshotDocumentVersionWrite.model_validate(request.model_dump())
    )
    return SnapshotDocumentVersionResult(status="CREATED", link=link)


def _blocked_link(warning: str) -> SnapshotDocumentVersionResult:
    return SnapshotDocumentVersionResult(status="BLOCKED", link=None, warnings=(warning,))
