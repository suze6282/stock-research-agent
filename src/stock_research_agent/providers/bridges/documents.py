"""Bridge verified raw document bodies into immutable Stage 6 version inputs."""

from __future__ import annotations

from datetime import date
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.documents.enums import (
    DocumentLanguage,
    SourceVersionStatus,
    TrustLevel,
)
from stock_research_agent.domain.documents.schemas import DocumentVersionWrite
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


class DocumentBridgeContext(FrozenProviderContract):
    logical_document_id: UUID
    source_document_id: UUID
    security_id: UUID
    provider_id: UUID
    source_payload_id: UUID
    version_number: int = Field(ge=1)
    supersedes_document_version_id: UUID | None
    storage_uri: str = Field(min_length=1, max_length=1024)
    mime_type: Literal["application/json", "application/pdf", "text/html", "text/plain"]
    checksum: Checksum
    byte_size: int = Field(ge=1, le=10_000_000)
    published_at: AwareUtcDateTime | None
    filed_at: AwareUtcDateTime | None
    period_end: date | None
    retrieved_at: AwareUtcDateTime
    document_language: DocumentLanguage
    trust_level: TrustLevel
    evidence_origin: Literal["SOURCE"]
    access_mode: Literal["OFFLINE", "ONLINE"]
    live_status: Literal["NOT_LIVE", "LIVE"]
    source_version_status: SourceVersionStatus
    research_as_of_time: AwareUtcDateTime
    derived_use_approved: bool
    raw_body_retention_approved: bool


class DocumentBridgeResult(FrozenProviderContract):
    staged_document_version_count: int = Field(ge=0)
    manifest_id: UUID
    manifest_checksum: Checksum
    raw_artifact_id: UUID
    document_checksum: Checksum
    parse_run_created: Literal[False] = False
    retrieval_run_created: Literal[False] = False


class DocumentBridgeRepository(Protocol):
    def add_version(self, value: DocumentVersionWrite) -> object: ...


class DocumentProviderBridge:
    """Persist only an immutable version input for an already-verified raw body."""

    def __init__(self, repository: DocumentBridgeRepository) -> None:
        self._repository = repository

    def stage(
        self,
        manifest: ProviderIngestionManifestRecord,
        batch: ProviderBatch,
        context: DocumentBridgeContext,
    ) -> DocumentBridgeResult:
        if not context.derived_use_approved or not context.raw_body_retention_approved:
            raise ValueError("DOCUMENT_DERIVED_STORAGE_NOT_APPROVED")
        if batch.record_count != 1 or manifest.record_count != 1:
            raise ValueError("DOCUMENT_BODY_RECORD_COUNT_INVALID")
        if manifest.manifest_checksum != batch.manifest_checksum:
            raise ValueError("DOCUMENT_MANIFEST_MISMATCH")
        if manifest.batch_checksum != batch.batch_checksum:
            raise ValueError("DOCUMENT_BATCH_CHECKSUM_MISMATCH")
        if manifest.synthetic_status in {
            ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
            ProviderSyntheticStatus.UNKNOWN,
        }:
            raise ValueError("SYNTHETIC_DOCUMENT_WRITE_FORBIDDEN")
        _ensure_not_future(context.published_at, context.research_as_of_time)
        _ensure_not_future(context.filed_at, context.research_as_of_time)
        _ensure_not_future(context.retrieved_at, context.research_as_of_time)

        record = batch.records[0]
        if record.raw_artifact_id != manifest.raw_artifact_id:
            raise ValueError("DOCUMENT_RAW_ARTIFACT_MISMATCH")
        if record.source_checksum != context.checksum:
            raise ValueError("DOCUMENT_RAW_CHECKSUM_MISMATCH")
        if record.synthetic_status is not manifest.synthetic_status:
            raise ValueError("DOCUMENT_SYNTHETIC_STATUS_MISMATCH")
        _ensure_not_future(record.source_published_at, context.research_as_of_time)
        if record.text_values.get("security_id") != str(context.security_id):
            raise ValueError("DOCUMENT_SECURITY_MISMATCH")
        if record.text_values.get("document_content_status") != "VERIFIED_BODY":
            raise ValueError("DOCUMENT_BODY_NOT_VERIFIED")

        write = DocumentVersionWrite(
            logical_document_id=context.logical_document_id,
            source_document_id=context.source_document_id,
            security_id=context.security_id,
            provider_id=context.provider_id,
            source_payload_id=context.source_payload_id,
            version_number=context.version_number,
            supersedes_document_version_id=context.supersedes_document_version_id,
            storage_uri=context.storage_uri,
            mime_type=context.mime_type,
            checksum_algorithm="sha256",
            checksum=context.checksum,
            byte_size=context.byte_size,
            published_at=context.published_at,
            filed_at=context.filed_at,
            period_end=context.period_end,
            retrieved_at=context.retrieved_at,
            document_language=context.document_language,
            trust_level=context.trust_level,
            evidence_origin=context.evidence_origin,
            access_mode=context.access_mode,
            live_status=context.live_status,
            source_version_status=context.source_version_status,
        )
        self._repository.add_version(write)
        return DocumentBridgeResult(
            staged_document_version_count=1,
            manifest_id=manifest.id,
            manifest_checksum=manifest.manifest_checksum,
            raw_artifact_id=manifest.raw_artifact_id,
            document_checksum=context.checksum,
            parse_run_created=False,
            retrieval_run_created=False,
        )


def _ensure_not_future(
    value: AwareUtcDateTime | None, research_as_of_time: AwareUtcDateTime
) -> None:
    if value is not None and value > research_as_of_time:
        raise ValueError("DOCUMENT_FUTURE_DATA")


__all__ = [
    "DocumentBridgeContext",
    "DocumentBridgeRepository",
    "DocumentBridgeResult",
    "DocumentProviderBridge",
]
