"""Persistence ports for immutable document evidence."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from stock_research_agent.domain.documents.schemas import (
    CitationContext,
    DocumentParseRunRecord,
    DocumentParseRunWrite,
    DocumentVersionRecord,
    DocumentVersionWrite,
    ParseCompletion,
    ParsedDocument,
    SnapshotBodyEvidenceRecord,
    SnapshotDocumentVersionRecord,
    SnapshotDocumentVersionWrite,
    SourceBodyRecord,
)


class DocumentVersionRepository(Protocol):
    def get_source_body(self, source_document_id: UUID) -> SourceBodyRecord | None: ...

    def get_logical_document_security_id(self, logical_document_id: UUID) -> UUID | None: ...

    def find_version(
        self, logical_document_id: UUID, checksum: str
    ) -> DocumentVersionRecord | None: ...

    def next_version_number(self, logical_document_id: UUID) -> int: ...

    def add_version(self, value: DocumentVersionWrite) -> DocumentVersionRecord: ...

    def acquire_version(
        self, value: DocumentVersionWrite
    ) -> tuple[DocumentVersionRecord, bool]: ...

    def add_snapshot_version_link(
        self, value: SnapshotDocumentVersionWrite
    ) -> SnapshotDocumentVersionRecord: ...

    def get_document_version(self, document_version_id: UUID) -> DocumentVersionRecord | None: ...

    def get_snapshot_body_evidence(
        self, snapshot_id: UUID, snapshot_item_id: UUID
    ) -> SnapshotBodyEvidenceRecord | None: ...

    def find_snapshot_version_link(
        self, snapshot_id: UUID, document_version_id: UUID
    ) -> SnapshotDocumentVersionRecord | None: ...


class DocumentArtifactRepository(Protocol):
    def get_document_version(self, document_version_id: UUID) -> DocumentVersionRecord | None: ...

    def find_parse_run(
        self,
        document_version_id: UUID,
        parser_name: str,
        parser_version: str,
        sanitizer_version: str,
        config_checksum: str,
    ) -> DocumentParseRunRecord | None: ...

    def create_parse_run(self, value: DocumentParseRunWrite) -> DocumentParseRunRecord: ...

    def acquire_parse_run(
        self, value: DocumentParseRunWrite
    ) -> tuple[DocumentParseRunRecord, bool]: ...

    def replace_running_artifacts(self, parse_run_id: UUID, value: ParsedDocument) -> None: ...

    def finish_parse_run(
        self, parse_run_id: UUID, completion: ParseCompletion
    ) -> DocumentParseRunRecord: ...

    def get_parsed_document(self, parse_run_id: UUID) -> ParsedDocument | None: ...


class CitationRepository(Protocol):
    def get_citation_context(self, citation_id: UUID) -> CitationContext | None: ...
