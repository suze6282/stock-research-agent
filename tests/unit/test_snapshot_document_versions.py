from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from stock_research_agent.domain.documents.enums import (
    DocumentLanguage,
    SourceVersionStatus,
    TrustLevel,
)
from stock_research_agent.domain.documents.identity import bind_version_to_snapshot
from stock_research_agent.domain.documents.schemas import (
    BindSnapshotDocumentVersionRequest,
    DocumentVersionRecord,
    DocumentVersionWrite,
    SnapshotBodyEvidenceRecord,
    SnapshotDocumentVersionRecord,
    SnapshotDocumentVersionWrite,
    SourceBodyRecord,
)

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
SNAPSHOT_ID = UUID("00000000-0000-0000-0000-000000000021")
ITEM_ID = UUID("00000000-0000-0000-0000-000000000022")


class SnapshotRepository:
    def __init__(self, body: SourceBodyRecord, version: DocumentVersionRecord) -> None:
        self.body = body
        self.versions = [version]
        self.links: list[SnapshotDocumentVersionRecord] = []
        self.evidence: SnapshotBodyEvidenceRecord | None = SnapshotBodyEvidenceRecord(
            snapshot_id=SNAPSHOT_ID,
            snapshot_item_id=ITEM_ID,
            security_id=version.security_id,
            provider_id=version.provider_id,
            category="SOURCE_DOCUMENTS",
            source_record_type="source_documents",
            source_record_id=version.source_document_id,
            source_published_at=version.published_at,
        )

    def get_source_body(self, source_document_id: UUID) -> SourceBodyRecord | None:
        return self.body if source_document_id == self.body.source_document_id else None

    def find_version(
        self, logical_document_id: UUID, checksum: str
    ) -> DocumentVersionRecord | None:
        return next(
            (
                row
                for row in self.versions
                if row.logical_document_id == logical_document_id and row.checksum == checksum
            ),
            None,
        )

    def next_version_number(self, logical_document_id: UUID) -> int:
        return 1 + len(
            [row for row in self.versions if row.logical_document_id == logical_document_id]
        )

    def add_version(self, value: DocumentVersionWrite) -> DocumentVersionRecord:
        row = DocumentVersionRecord(id=uuid4(), created_at=NOW, **value.model_dump())
        self.versions.append(row)
        return row

    def add_snapshot_version_link(
        self, value: SnapshotDocumentVersionWrite
    ) -> SnapshotDocumentVersionRecord:
        row = SnapshotDocumentVersionRecord(created_at=NOW, **value.model_dump())
        self.links.append(row)
        return row

    def get_document_version(self, document_version_id: UUID) -> DocumentVersionRecord | None:
        return next((row for row in self.versions if row.id == document_version_id), None)

    def get_snapshot_body_evidence(
        self, snapshot_id: UUID, snapshot_item_id: UUID
    ) -> SnapshotBodyEvidenceRecord | None:
        if (
            self.evidence is not None
            and self.evidence.snapshot_id == snapshot_id
            and self.evidence.snapshot_item_id == snapshot_item_id
        ):
            return self.evidence
        return None

    def find_snapshot_version_link(
        self, snapshot_id: UUID, document_version_id: UUID
    ) -> SnapshotDocumentVersionRecord | None:
        return next(
            (
                row
                for row in self.links
                if row.snapshot_id == snapshot_id and row.document_version_id == document_version_id
            ),
            None,
        )


def _arrange() -> tuple[SnapshotRepository, BindSnapshotDocumentVersionRequest]:
    body = SourceBodyRecord(
        source_document_id=uuid4(),
        security_id=uuid4(),
        provider_id=uuid4(),
        source_payload_id=uuid4(),
        document_status="AVAILABLE",
        storage_uri="blob://memory/0123456789abcdef0123456789abcdef",
        checksum="a" * 64,
        byte_size=10,
        mime_type="text/plain",
        published_at=NOW,
        retrieved_at=NOW,
    )
    version = DocumentVersionRecord(
        id=uuid4(),
        logical_document_id=uuid4(),
        source_document_id=body.source_document_id,
        security_id=body.security_id,
        provider_id=body.provider_id,
        source_payload_id=body.source_payload_id,
        version_number=1,
        supersedes_document_version_id=None,
        storage_uri=body.storage_uri,
        mime_type=body.mime_type,
        checksum_algorithm="sha256",
        checksum=body.checksum,
        byte_size=body.byte_size,
        published_at=body.published_at,
        filed_at=None,
        period_end=None,
        retrieved_at=body.retrieved_at,
        document_language=DocumentLanguage.EN_US,
        trust_level=TrustLevel.TEST_FIXTURE,
        evidence_origin="SYNTHETIC_TEST_ONLY",
        access_mode="OFFLINE",
        live_status="NOT_LIVE",
        source_version_status=SourceVersionStatus.ACTIVE,
        created_at=NOW,
    )
    repository = SnapshotRepository(body, version)
    return repository, BindSnapshotDocumentVersionRequest(
        snapshot_id=SNAPSHOT_ID,
        document_version_id=version.id,
        snapshot_item_id=ITEM_ID,
    )


def test_bind_snapshot_document_version_creates_exact_body_link() -> None:
    repository, request = _arrange()

    result = bind_version_to_snapshot(repository, request)

    assert result.status == "CREATED"
    assert result.link is repository.links[0]


def test_bind_snapshot_document_version_is_idempotent() -> None:
    repository, request = _arrange()

    first = bind_version_to_snapshot(repository, request)
    second = bind_version_to_snapshot(repository, request)

    assert first.link == second.link
    assert second.status == "REUSED"
    assert len(repository.links) == 1


def test_filing_metadata_item_cannot_satisfy_body_relation() -> None:
    repository, request = _arrange()
    assert repository.evidence is not None
    repository.evidence = repository.evidence.model_copy(update={"category": "FILING_METADATA"})

    result = bind_version_to_snapshot(repository, request)

    assert result.status == "BLOCKED"
    assert result.warnings == ("SNAPSHOT_ITEM_IS_NOT_DOCUMENT_BODY",)
    assert repository.links == []


def test_mismatched_source_record_cannot_be_attached() -> None:
    repository, request = _arrange()
    assert repository.evidence is not None
    repository.evidence = repository.evidence.model_copy(update={"source_record_id": uuid4()})

    result = bind_version_to_snapshot(repository, request)

    assert result.status == "BLOCKED"
    assert result.warnings == ("SNAPSHOT_ITEM_DOCUMENT_VERSION_MISMATCH",)
    assert repository.links == []


def test_missing_version_or_snapshot_item_is_blocked() -> None:
    repository, request = _arrange()
    repository.versions.clear()
    assert bind_version_to_snapshot(repository, request).warnings == ("DOCUMENT_VERSION_NOT_FOUND",)

    repository, request = _arrange()
    repository.evidence = None
    assert bind_version_to_snapshot(repository, request).warnings == ("SNAPSHOT_ITEM_NOT_FOUND",)
