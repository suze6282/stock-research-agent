from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from stock_research_agent.domain.documents.enums import (
    DocumentLanguage,
    SourceVersionStatus,
    TrustLevel,
)
from stock_research_agent.domain.documents.identity import DocumentVersionService
from stock_research_agent.domain.documents.schemas import (
    DocumentVersionRecord,
    DocumentVersionWrite,
    RegisterDocumentVersionRequest,
    SnapshotDocumentVersionRecord,
    SnapshotDocumentVersionWrite,
    SourceBodyRecord,
)
from stock_research_agent.infrastructure.blob_storage import InMemoryBlobStorage

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
LOGICAL_ID = UUID("00000000-0000-0000-0000-000000000011")
SECURITY_ID = UUID("00000000-0000-0000-0000-000000000012")
SOURCE_ID = UUID("00000000-0000-0000-0000-000000000013")
PROVIDER_ID = UUID("00000000-0000-0000-0000-000000000014")
PAYLOAD_ID = UUID("00000000-0000-0000-0000-000000000015")


class FakeVersionRepository:
    def __init__(self, body: SourceBodyRecord) -> None:
        self.body = body
        self.logical_security_id = body.security_id
        self.race_winner: DocumentVersionRecord | None = None
        self.versions: list[DocumentVersionRecord] = []
        self.links: list[SnapshotDocumentVersionRecord] = []

    def get_logical_document_security_id(self, logical_document_id: UUID) -> UUID | None:
        return self.logical_security_id

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
        return 1 + max(
            (
                row.version_number
                for row in self.versions
                if row.logical_document_id == logical_document_id
            ),
            default=0,
        )

    def add_version(self, value: DocumentVersionWrite) -> DocumentVersionRecord:
        row = DocumentVersionRecord(
            id=uuid4(),
            created_at=NOW,
            **value.model_dump(),
        )
        self.versions.append(row)
        return row

    def acquire_version(self, value: DocumentVersionWrite) -> tuple[DocumentVersionRecord, bool]:
        if self.race_winner is not None:
            self.versions.append(self.race_winner)
            return self.race_winner, False
        existing = self.find_version(value.logical_document_id, value.checksum)
        if existing is not None:
            return existing, False
        return self.add_version(value), True

    def get_document_version(self, document_version_id: UUID) -> DocumentVersionRecord | None:
        return next((row for row in self.versions if row.id == document_version_id), None)

    def add_snapshot_version_link(
        self, value: SnapshotDocumentVersionWrite
    ) -> SnapshotDocumentVersionRecord:
        row = SnapshotDocumentVersionRecord(created_at=NOW, **value.model_dump())
        self.links.append(row)
        return row


def _arrange(
    content: bytes = b"verified synthetic body",
) -> tuple[DocumentVersionService, FakeVersionRepository, RegisterDocumentVersionRequest]:
    storage = InMemoryBlobStorage(
        max_blob_bytes=10_000_000,
        key_factory=lambda: "0123456789abcdef0123456789abcdef",
    )
    metadata = storage.put(content, content_type="text/plain")
    body = SourceBodyRecord(
        source_document_id=SOURCE_ID,
        security_id=SECURITY_ID,
        provider_id=PROVIDER_ID,
        source_payload_id=PAYLOAD_ID,
        document_status="AVAILABLE",
        storage_uri=metadata.uri,
        checksum=metadata.checksum_sha256,
        byte_size=metadata.size_bytes,
        mime_type=metadata.content_type,
        published_at=NOW,
        retrieved_at=NOW,
    )
    repository = FakeVersionRepository(body)
    request = RegisterDocumentVersionRequest(
        logical_document_id=LOGICAL_ID,
        source_body=body,
        document_language=DocumentLanguage.EN_US,
        trust_level=TrustLevel.TEST_FIXTURE,
        evidence_origin="SYNTHETIC_TEST_ONLY",
        access_mode="OFFLINE",
        live_status="NOT_LIVE",
        source_version_status=SourceVersionStatus.ACTIVE,
    )
    return DocumentVersionService(repository, storage), repository, request


def test_register_creates_first_immutable_version() -> None:
    service, repository, request = _arrange()

    result = service.register(request)

    assert result.status == "CREATED"
    assert result.version is repository.versions[0]
    assert result.version.version_number == 1
    assert result.version.checksum == request.source_body.checksum


def test_register_reuses_same_logical_document_and_checksum() -> None:
    service, repository, request = _arrange()

    first = service.register(request)
    second = service.register(request)

    assert second.status == "REUSED"
    assert second.version == first.version
    assert len(repository.versions) == 1


def test_reuse_revalidates_blob_and_rejects_policy_conflict() -> None:
    service, repository, request = _arrange()
    first = service.register(request)
    assert first.version is not None

    missing_storage = InMemoryBlobStorage(max_blob_bytes=10_000_000)
    missing_blob = DocumentVersionService(repository, missing_storage).register(request)
    policy_conflict = service.register(
        request.model_copy(update={"source_version_status": SourceVersionStatus.WITHDRAWN})
    )

    assert missing_blob.status == "BLOCKED"
    assert missing_blob.warnings == ("SOURCE_BODY_BLOB_METADATA_MISMATCH",)
    assert policy_conflict.status == "BLOCKED"
    assert policy_conflict.warnings == ("DOCUMENT_VERSION_POLICY_CONFLICT",)
    assert len(repository.versions) == 1


def test_changed_bytes_create_next_version_without_mutating_old_version() -> None:
    first_service, repository, first_request = _arrange(b"version one")
    first = first_service.register(first_request)
    old_dump = first.version.model_dump() if first.version else {}

    second_storage = InMemoryBlobStorage(
        max_blob_bytes=10_000_000,
        key_factory=lambda: "fedcba9876543210fedcba9876543210",
    )
    metadata = second_storage.put(b"version two", content_type="text/plain")
    second_body = first_request.source_body.model_copy(
        update={
            "source_document_id": uuid4(),
            "source_payload_id": uuid4(),
            "storage_uri": metadata.uri,
            "checksum": metadata.checksum_sha256,
            "byte_size": metadata.size_bytes,
        }
    )
    repository.body = second_body
    second_request = first_request.model_copy(
        update={
            "source_body": second_body,
            "supersedes_document_version_id": first.version.id if first.version else None,
        }
    )

    second = DocumentVersionService(repository, second_storage).register(second_request)

    assert second.status == "CREATED"
    assert second.version is not None and second.version.version_number == 2
    assert second.version.supersedes_document_version_id == first.version.id
    assert repository.versions[0].model_dump() == old_dump


def test_checksum_collision_with_incompatible_metadata_fails_without_write() -> None:
    service, repository, request = _arrange()
    service.register(request)
    incompatible = request.model_copy(
        update={"source_body": request.source_body.model_copy(update={"mime_type": "text/html"})}
    )
    repository.body = incompatible.source_body

    result = service.register(incompatible)

    assert result.status == "BLOCKED"
    assert result.warnings == ("DOCUMENT_VERSION_METADATA_CONFLICT",)
    assert len(repository.versions) == 1


def test_blob_checksum_mismatch_is_blocked() -> None:
    service, repository, request = _arrange()
    invalid = request.model_copy(
        update={"source_body": request.source_body.model_copy(update={"checksum": "b" * 64})}
    )
    repository.body = invalid.source_body

    result = service.register(invalid)

    assert result.status == "BLOCKED"
    assert result.warnings == ("SOURCE_BODY_BLOB_METADATA_MISMATCH",)
    assert repository.versions == []


def test_missing_stable_logical_identity_is_blocked() -> None:
    service, repository, request = _arrange()
    request_without_identity = request.model_copy(update={"logical_document_id": None})

    result = service.register(request_without_identity)

    assert result.status == "BLOCKED"
    assert result.warnings == ("STABLE_DOCUMENT_IDENTITY_REQUIRED",)
    assert repository.versions == []


def test_logical_document_security_must_match_source_body_security() -> None:
    service, repository, request = _arrange()
    repository.logical_security_id = uuid4()

    result = service.register(request)

    assert result.status == "BLOCKED"
    assert result.warnings == ("LOGICAL_DOCUMENT_SECURITY_MISMATCH",)
    assert repository.versions == []


def test_concurrent_winner_with_incompatible_policy_is_rejected() -> None:
    service, repository, request = _arrange()
    winner = DocumentVersionRecord(
        id=uuid4(),
        created_at=NOW,
        **DocumentVersionWrite(
            logical_document_id=LOGICAL_ID,
            source_document_id=request.source_body.source_document_id,
            security_id=request.source_body.security_id,
            provider_id=request.source_body.provider_id,
            source_payload_id=request.source_body.source_payload_id,
            version_number=1,
            supersedes_document_version_id=None,
            storage_uri=request.source_body.storage_uri,
            mime_type=request.source_body.mime_type,
            checksum_algorithm="sha256",
            checksum=request.source_body.checksum,
            byte_size=request.source_body.byte_size,
            published_at=request.source_body.published_at,
            filed_at=None,
            period_end=None,
            retrieved_at=request.source_body.retrieved_at,
            document_language=request.document_language,
            trust_level=TrustLevel.APPROVED_PROVIDER,
            evidence_origin=request.evidence_origin,
            access_mode=request.access_mode,
            live_status=request.live_status,
            source_version_status=request.source_version_status,
        ).model_dump(),
    )

    repository.race_winner = winner

    result = service.register(request)

    assert result.status == "BLOCKED"
    assert result.warnings == ("DOCUMENT_VERSION_POLICY_CONFLICT",)


def test_supersedes_relation_requires_same_logical_document_and_newer_version() -> None:
    first_service, repository, first_request = _arrange(b"version one")
    first = first_service.register(first_request)
    assert first.version is not None

    second_storage = InMemoryBlobStorage(
        max_blob_bytes=10_000_000,
        key_factory=lambda: "fedcba9876543210fedcba9876543210",
    )
    metadata = second_storage.put(b"version two", content_type="text/plain")
    second_body = first_request.source_body.model_copy(
        update={
            "source_document_id": uuid4(),
            "source_payload_id": uuid4(),
            "storage_uri": metadata.uri,
            "checksum": metadata.checksum_sha256,
            "byte_size": metadata.size_bytes,
        }
    )
    repository.body = second_body

    wrong_logical = DocumentVersionService(repository, second_storage).register(
        first_request.model_copy(
            update={
                "logical_document_id": uuid4(),
                "source_body": second_body,
                "supersedes_document_version_id": first.version.id,
            }
        )
    )
    wrong_order = DocumentVersionService(repository, second_storage).register(
        first_request.model_copy(
            update={
                "source_body": second_body,
                "version_number": 1,
                "supersedes_document_version_id": first.version.id,
            }
        )
    )

    assert wrong_logical.status == "BLOCKED"
    assert wrong_logical.warnings == ("SUPERSEDES_VERSION_LOGICAL_DOCUMENT_MISMATCH",)
    assert wrong_order.status == "BLOCKED"
    assert wrong_order.warnings == ("SUPERSEDES_VERSION_ORDER_INVALID",)
    assert len(repository.versions) == 1
