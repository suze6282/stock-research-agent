"""SQLAlchemy persistence for immutable Stage 6 retrieval runs and cache reads."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stock_research_agent.db.models.data_access import SnapshotItem, SourceDocument
from stock_research_agent.db.models.knowledge import (
    CitationAnchor,
    DocumentChunk,
    DocumentPage,
    DocumentParseRun,
    DocumentSection,
    DocumentVersion,
    LexicalIndexVersion,
    LexicalPosting,
    LogicalDocument,
    RetrievalHit,
    RetrievalRun,
    SnapshotDocumentVersion,
)
from stock_research_agent.domain.documents.citations import CitationVerifier, create_citation
from stock_research_agent.domain.documents.enums import (
    ContentKind,
    DocumentLanguage,
    LocatorType,
    PageStatus,
    ParseStatus,
    SourceVersionStatus,
    TrustLevel,
)
from stock_research_agent.domain.documents.schemas import (
    AccessMode,
    CitationAnchorRecord,
    CitationContext,
    CitationScope,
    CreateCitationRequest,
    DocumentChunkDraft,
    DocumentParseRunRecord,
    DocumentParseRunWrite,
    DocumentVersionRecord,
    DocumentVersionWrite,
    EvidenceOrigin,
    LiveStatus,
    ParseCompletion,
    ParsedDocument,
    ParsedPage,
    ParsedSection,
    SnapshotBodyEvidenceRecord,
    SnapshotDocumentVersionRecord,
    SnapshotDocumentVersionWrite,
    SourceBodyRecord,
)
from stock_research_agent.domain.retrieval.enums import (
    IndexStatus,
    RetrievalMode,
    RetrievalStatus,
)
from stock_research_agent.domain.retrieval.schemas import (
    EvidenceBundle,
    EvidenceItem,
    IndexableChunk,
    LexicalBuildRequest,
    LexicalIndexResult,
    LexicalPostingDraft,
    RetrievalCompletion,
    RetrievalHitRecord,
    RetrievalHitWrite,
    RetrievalRequest,
    RetrievalRunRecord,
    RetrievalRunWrite,
)
from stock_research_agent.infrastructure.blob_storage import BlobStorage, BlobStorageError


class SqlAlchemyKnowledgeRepository:
    def __init__(self, session: Session, blob_storage: BlobStorage | None = None) -> None:
        self._session = session
        self._blob_storage = blob_storage

    def get_source_body(self, source_document_id: UUID) -> SourceBodyRecord | None:
        row = self._session.get(SourceDocument, source_document_id)
        if (
            row is None
            or row.document_status != "AVAILABLE"
            or row.storage_uri is None
            or row.checksum is None
            or row.byte_size is None
            or row.mime_type is None
        ):
            return None
        return SourceBodyRecord(
            source_document_id=row.id,
            security_id=row.security_id,
            provider_id=row.provider_id,
            source_payload_id=row.source_payload_id,
            document_status="AVAILABLE",
            storage_uri=row.storage_uri,
            checksum=row.checksum,
            byte_size=row.byte_size,
            mime_type=row.mime_type,
            published_at=row.published_at,
            filed_at=row.filed_at,
            period_end=row.period_end,
            retrieved_at=row.retrieved_at,
        )

    def get_logical_document_security_id(self, logical_document_id: UUID) -> UUID | None:
        return self._session.scalar(
            select(LogicalDocument.security_id).where(LogicalDocument.id == logical_document_id)
        )

    def find_version(
        self, logical_document_id: UUID, checksum: str
    ) -> DocumentVersionRecord | None:
        row = self._session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.logical_document_id == logical_document_id,
                DocumentVersion.checksum == checksum,
            )
        )
        return None if row is None else _document_version_record(row)

    def next_version_number(self, logical_document_id: UUID) -> int:
        current = self._session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.logical_document_id == logical_document_id
            )
        )
        return int(current or 0) + 1

    def add_version(self, value: DocumentVersionWrite) -> DocumentVersionRecord:
        return self.acquire_version(value)[0]

    def acquire_version(self, value: DocumentVersionWrite) -> tuple[DocumentVersionRecord, bool]:
        existing = self.find_version(value.logical_document_id, value.checksum)
        if existing is not None:
            return existing, False
        row = DocumentVersion(**value.model_dump(mode="python"))
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            winner = self.find_version(value.logical_document_id, value.checksum)
            if winner is None:
                raise
            return winner, False
        return _document_version_record(row), True

    def get_document_version(self, document_version_id: UUID) -> DocumentVersionRecord | None:
        row = self._session.get(DocumentVersion, document_version_id)
        return None if row is None else _document_version_record(row)

    def add_snapshot_version_link(
        self, value: SnapshotDocumentVersionWrite
    ) -> SnapshotDocumentVersionRecord:
        existing = self.find_snapshot_version_link(value.snapshot_id, value.document_version_id)
        if existing is not None:
            return existing
        row = SnapshotDocumentVersion(**value.model_dump(mode="python"))
        self._session.add(row)
        self._session.flush()
        return _snapshot_version_record(row)

    def find_snapshot_version_link(
        self, snapshot_id: UUID, document_version_id: UUID
    ) -> SnapshotDocumentVersionRecord | None:
        row = self._session.get(SnapshotDocumentVersion, (snapshot_id, document_version_id))
        return None if row is None else _snapshot_version_record(row)

    def get_snapshot_body_evidence(
        self, snapshot_id: UUID, snapshot_item_id: UUID
    ) -> SnapshotBodyEvidenceRecord | None:
        row = self._session.scalar(
            select(SnapshotItem).where(
                SnapshotItem.id == snapshot_item_id,
                SnapshotItem.snapshot_id == snapshot_id,
            )
        )
        if row is None or row.source_record_type != "source_documents":
            return None
        document = self._session.get(SourceDocument, row.source_record_id)
        if document is None:
            return None
        return SnapshotBodyEvidenceRecord(
            snapshot_id=row.snapshot_id,
            snapshot_item_id=row.id,
            security_id=document.security_id,
            provider_id=row.provider_id,
            category=cast(Literal["SOURCE_DOCUMENTS", "FILING_METADATA"], row.category),
            source_record_type="source_documents",
            source_record_id=row.source_record_id,
            source_published_at=row.source_published_at,
        )

    def find_parse_run(
        self,
        document_version_id: UUID,
        parser_name: str,
        parser_version: str,
        sanitizer_version: str,
        config_checksum: str,
    ) -> DocumentParseRunRecord | None:
        row = self._session.scalar(
            select(DocumentParseRun).where(
                DocumentParseRun.document_version_id == document_version_id,
                DocumentParseRun.parser_name == parser_name,
                DocumentParseRun.parser_version == parser_version,
                DocumentParseRun.sanitizer_version == sanitizer_version,
                DocumentParseRun.config_checksum == config_checksum,
            )
        )
        return None if row is None else _parse_run_record(row)

    def create_parse_run(self, value: DocumentParseRunWrite) -> DocumentParseRunRecord:
        return self.acquire_parse_run(value)[0]

    def acquire_parse_run(
        self, value: DocumentParseRunWrite
    ) -> tuple[DocumentParseRunRecord, bool]:
        existing = self.find_parse_run(
            value.document_version_id,
            value.parser_name,
            value.parser_version,
            value.sanitizer_version,
            value.config_checksum,
        )
        if existing is not None:
            return existing, False
        row = DocumentParseRun(
            **value.model_dump(mode="python"),
            canonical_text=None,
            canonical_text_checksum=None,
            warnings=[],
            started_at=self._session.scalar(select(func.now())),
            completed_at=None,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            winner = self.find_parse_run(
                value.document_version_id,
                value.parser_name,
                value.parser_version,
                value.sanitizer_version,
                value.config_checksum,
            )
            if winner is None:
                raise
            return winner, False
        return _parse_run_record(row), True

    def replace_running_artifacts(self, parse_run_id: UUID, value: ParsedDocument) -> None:
        run = self._session.get(DocumentParseRun, parse_run_id)
        if run is None or run.completed_at is not None or run.status != ParseStatus.RUNNING.value:
            raise ValueError("parse run is not mutable")
        if self._session.scalar(
            select(func.count())
            .select_from(DocumentPage)
            .where(DocumentPage.parse_run_id == parse_run_id)
        ):
            raise ValueError("parse artifacts already exist")
        run.canonical_text = value.canonical_text
        for page in value.pages:
            self._session.add(
                DocumentPage(
                    parse_run_id=parse_run_id,
                    page_number=page.page_number,
                    text=page.text,
                    text_checksum=page.text_checksum,
                    character_count=page.character_count,
                    status=page.status.value,
                    warnings=list(page.warnings),
                )
            )
        section_ids: dict[str, UUID] = {}
        for section in sorted(value.sections, key=lambda item: (item.level, item.section_path)):
            row = DocumentSection(
                parse_run_id=parse_run_id,
                parent_section_id=(
                    None
                    if section.parent_section_path is None
                    else section_ids[section.parent_section_path]
                ),
                section_path=section.section_path,
                level=section.level,
                title=section.title,
                locator_type=section.locator_type.value,
                start_page=section.start_page,
                end_page=section.end_page,
                start_offset=section.start_offset,
                end_offset=section.end_offset,
                text_checksum=section.text_checksum,
                content_kind=section.content_kind.value,
            )
            self._session.add(row)
            self._session.flush()
            section_ids[section.section_path] = row.id
        self._session.flush()

    def finish_parse_run(
        self, parse_run_id: UUID, completion: ParseCompletion
    ) -> DocumentParseRunRecord:
        row = self._session.get(DocumentParseRun, parse_run_id)
        if row is None or row.completed_at is not None:
            raise ValueError("parse run is not mutable")
        row.status = completion.status.value
        row.canonical_text_checksum = completion.canonical_text_checksum
        row.warnings = list(completion.warnings)
        row.completed_at = self._session.scalar(select(func.now()))
        self._session.flush()
        return _parse_run_record(row)

    def get_parsed_document(self, parse_run_id: UUID) -> ParsedDocument | None:
        run = self._session.get(DocumentParseRun, parse_run_id)
        if run is None or run.completed_at is None or run.canonical_text is None:
            return None
        pages = self._session.scalars(
            select(DocumentPage)
            .where(DocumentPage.parse_run_id == parse_run_id)
            .order_by(DocumentPage.page_number)
        ).all()
        sections = self._session.scalars(
            select(DocumentSection)
            .where(DocumentSection.parse_run_id == parse_run_id)
            .order_by(DocumentSection.level, DocumentSection.section_path)
        ).all()
        paths = {section.id: section.section_path for section in sections}
        if run.canonical_text_checksum is None:
            return None
        return ParsedDocument(
            canonical_text=run.canonical_text,
            canonical_text_checksum=run.canonical_text_checksum,
            pages=tuple(
                ParsedPage(
                    page_number=page.page_number,
                    text=page.text,
                    text_checksum=page.text_checksum,
                    character_count=page.character_count,
                    status=PageStatus(page.status),
                    warnings=tuple(page.warnings),
                )
                for page in pages
            ),
            sections=tuple(
                ParsedSection(
                    section_path=section.section_path,
                    parent_section_path=(
                        None
                        if section.parent_section_id is None
                        else paths[section.parent_section_id]
                    ),
                    level=section.level,
                    title=section.title,
                    locator_type=LocatorType(section.locator_type),
                    start_page=section.start_page,
                    end_page=section.end_page,
                    start_offset=section.start_offset,
                    end_offset=section.end_offset,
                    text_checksum=section.text_checksum,
                    content_kind=ContentKind(section.content_kind),
                )
                for section in sections
            ),
            status=ParseStatus(run.status),
            warnings=tuple(run.warnings),
            parser_metadata={"persistence": "postgresql"},
        )

    def add_chunks_and_citations(
        self,
        *,
        parse_run_id: UUID,
        document_version_id: UUID,
        chunks: tuple[DocumentChunkDraft, ...],
    ) -> tuple[UUID, ...]:
        run = self._session.get(DocumentParseRun, parse_run_id)
        version = self._session.get(DocumentVersion, document_version_id)
        if run is None or run.completed_at is None or version is None:
            raise ValueError("terminal parse run and document version are required")
        if run.canonical_text_checksum is None:
            raise ValueError("canonical parse checksum is required")
        existing = self._session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.parse_run_id == parse_run_id)
            .order_by(DocumentChunk.chunk_index)
        ).all()
        if existing:
            if tuple(row.checksum for row in existing) != tuple(chunk.checksum for chunk in chunks):
                raise ValueError("chunk generation conflict")
            return tuple(row.id for row in existing)
        pages = self._session.scalars(
            select(DocumentPage).where(DocumentPage.parse_run_id == parse_run_id)
        ).all()
        sections = self._session.scalars(
            select(DocumentSection).where(DocumentSection.parse_run_id == parse_run_id)
        ).all()
        page_ids = {page.page_number: page.id for page in pages}
        section_ids = {section.section_path: section.id for section in sections}
        ids: list[UUID] = []
        for draft in chunks:
            row = DocumentChunk(
                parse_run_id=parse_run_id,
                document_version_id=document_version_id,
                **draft.model_dump(
                    mode="python",
                    exclude={"warnings", "section_path", "html_anchor", "json_pointer"},
                ),
                warnings=list(draft.warnings),
            )
            self._session.add(row)
            self._session.flush()
            page_id = (
                page_ids.get(draft.start_page)
                if draft.start_page is not None and draft.start_page == draft.end_page
                else None
            )
            section_id = None if draft.section_path is None else section_ids.get(draft.section_path)
            citation = create_citation(
                CreateCitationRequest(
                    document_version_id=document_version_id,
                    parse_run_id=parse_run_id,
                    page_id=page_id,
                    section_id=section_id,
                    chunk_id=row.id,
                    locator_type=draft.locator_type,
                    start_page=draft.start_page,
                    end_page=draft.end_page,
                    html_anchor=draft.html_anchor,
                    json_pointer=draft.json_pointer,
                    start_offset=draft.start_offset,
                    end_offset=draft.end_offset,
                    excerpt=draft.text,
                    excerpt_checksum=hashlib.sha256(draft.text.encode()).hexdigest(),
                    canonical_text_checksum=run.canonical_text_checksum,
                    document_checksum=version.checksum,
                    parser_version=run.parser_version,
                    sanitizer_version=run.sanitizer_version,
                )
            )
            self._session.add(
                CitationAnchor(
                    document_version_id=document_version_id,
                    parse_run_id=parse_run_id,
                    page_id=citation.page_id,
                    section_id=citation.section_id,
                    chunk_id=row.id,
                    locator_type=citation.locator_type.value,
                    locator={
                        "start_page": citation.start_page,
                        "end_page": citation.end_page,
                        "section_path": draft.section_path,
                        "html_anchor": citation.html_anchor,
                        "json_pointer": citation.json_pointer,
                        "start_offset": citation.start_offset,
                        "end_offset": citation.end_offset,
                    },
                    excerpt=citation.excerpt,
                    excerpt_checksum=citation.excerpt_checksum,
                    canonical_text_checksum=citation.canonical_text_checksum,
                    document_checksum=citation.document_checksum,
                    locator_checksum=citation.locator_checksum,
                    citation_version=citation.citation_version,
                    parser_version=citation.parser_version,
                    sanitizer_version=citation.sanitizer_version,
                )
            )
            ids.append(row.id)
        self._session.flush()
        return tuple(ids)

    def get_or_create_logical_document(self, source_document_id: UUID) -> UUID | None:
        source = self._session.get(SourceDocument, source_document_id)
        if source is None:
            return None
        identity = source.accession_number or source.provider_document_id or source.announcement_id
        if identity is None:
            return None
        scheme = (
            "ACCESSION_NUMBER"
            if source.accession_number
            else "PROVIDER_DOCUMENT_ID"
            if source.provider_document_id
            else "ANNOUNCEMENT_ID"
        )
        normalized = " ".join(identity.casefold().split())
        existing = self._session.scalar(
            select(LogicalDocument).where(
                LogicalDocument.security_id == source.security_id,
                LogicalDocument.identity_scheme == scheme,
                LogicalDocument.normalized_identity_value == normalized,
            )
        )
        if existing is not None:
            return existing.id
        row = LogicalDocument(
            security_id=source.security_id,
            document_type=source.document_type,
            form_type=source.form_type,
            identity_scheme=scheme,
            identity_value=identity,
            normalized_identity_value=normalized,
            title=source.title,
        )
        self._session.add(row)
        self._session.flush()
        return row.id

    def list_indexable_chunks(self, security_id: UUID) -> tuple[IndexableChunk, ...]:
        rows = self._session.execute(
            select(DocumentChunk, DocumentVersion, LogicalDocument)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(LogicalDocument, LogicalDocument.id == DocumentVersion.logical_document_id)
            .where(DocumentVersion.security_id == security_id)
            .order_by(DocumentVersion.id, DocumentChunk.chunk_index, DocumentChunk.id)
        ).all()
        result: list[IndexableChunk] = []
        for chunk, version, logical in rows:
            _superseder_id, superseded_at, supersession_time_unknown = self._supersession_state(
                version.id
            )
            snapshot_ids = tuple(
                self._session.scalars(
                    select(SnapshotDocumentVersion.snapshot_id)
                    .where(SnapshotDocumentVersion.document_version_id == version.id)
                    .order_by(SnapshotDocumentVersion.snapshot_id)
                ).all()
            )
            citation = self._session.scalar(
                select(CitationAnchor)
                .where(CitationAnchor.chunk_id == chunk.id)
                .order_by(CitationAnchor.id)
                .limit(1)
            )
            result.append(
                IndexableChunk(
                    chunk_id=chunk.id,
                    document_version_id=version.id,
                    document_checksum=version.checksum,
                    security_id=security_id,
                    published_at=version.published_at,
                    snapshot_ids=snapshot_ids,
                    chunk_index=chunk.chunk_index,
                    locator_checksum=(
                        chunk.checksum if citation is None else citation.locator_checksum
                    ),
                    text=chunk.text,
                    section_title=None,
                    document_type=logical.document_type,
                    language=DocumentLanguage(version.document_language),
                    trust_level=TrustLevel(version.trust_level),
                    superseded_at=superseded_at,
                    supersession_time_unknown=supersession_time_unknown,
                )
            )
        return tuple(result)

    def _supersession_state(
        self, document_version_id: UUID
    ) -> tuple[UUID | None, datetime | None, bool]:
        superseders = self._session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.supersedes_document_version_id == document_version_id)
            .order_by(DocumentVersion.version_number, DocumentVersion.id)
        ).all()
        if not superseders:
            return None, None, False
        known_times = tuple(row.published_at for row in superseders if row.published_at is not None)
        return (
            superseders[0].id,
            min(known_times) if known_times else None,
            any(row.published_at is None for row in superseders),
        )

    def citation_ids_for_chunks(self, chunk_ids: tuple[UUID, ...]) -> dict[UUID, UUID]:
        if not chunk_ids:
            return {}
        rows = self._session.scalars(
            select(CitationAnchor)
            .where(CitationAnchor.chunk_id.in_(chunk_ids))
            .order_by(CitationAnchor.chunk_id, CitationAnchor.id)
        ).all()
        result: dict[UUID, UUID] = {}
        for row in rows:
            if row.chunk_id is not None:
                result.setdefault(row.chunk_id, row.id)
        return result

    def persist_lexical_index(
        self, request: LexicalBuildRequest, result: LexicalIndexResult
    ) -> LexicalIndexResult:
        if result.index_version_id is None or result.document_set_checksum is None:
            raise ValueError("complete lexical index metadata is required")
        existing = self._session.get(LexicalIndexVersion, result.index_version_id)
        if existing is not None:
            return self.load_lexical_index(result.index_version_id)
        fingerprint = hashlib.sha256(
            f"{result.index_version_id}:{result.document_set_checksum}".encode()
        ).hexdigest()
        row = LexicalIndexVersion(
            id=result.index_version_id,
            name=request.index_name,
            security_id=request.security_id,
            snapshot_id=request.snapshot_id,
            index_as_of_time=request.index_as_of_time,
            tokenizer_version=request.tokenizer_version,
            chunk_version=request.chunk_version,
            scoring_version=request.scoring_version,
            document_set_checksum=result.document_set_checksum,
            fingerprint=fingerprint,
            document_count=result.document_count,
            chunk_count=result.chunk_count,
            average_length=result.average_chunk_length or 0,
            status=result.status.value,
            completed_at=self._session.scalar(select(func.now())),
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
                self._session.add_all(
                    LexicalPosting(
                        index_version_id=row.id,
                        token=posting.token,
                        chunk_id=posting.chunk_id,
                        term_frequency=posting.term_frequency,
                        field_kind=posting.field_kind,
                        positions=list(posting.positions),
                    )
                    for posting in result.postings
                )
                self._session.flush()
        except IntegrityError:
            return self.load_lexical_index(result.index_version_id)
        return result

    def find_lexical_index(
        self,
        *,
        security_id: UUID,
        snapshot_id: UUID | None,
        index_as_of_time: datetime | None,
    ) -> LexicalIndexResult | None:
        statement = select(LexicalIndexVersion).where(
            LexicalIndexVersion.security_id == security_id,
            LexicalIndexVersion.status == "COMPLETE",
        )
        if snapshot_id is not None:
            statement = statement.where(LexicalIndexVersion.snapshot_id == snapshot_id)
        else:
            statement = statement.where(
                LexicalIndexVersion.snapshot_id.is_(None),
                LexicalIndexVersion.index_as_of_time == index_as_of_time,
            )
        row = self._session.scalar(
            statement.order_by(
                LexicalIndexVersion.completed_at.desc(), LexicalIndexVersion.id
            ).limit(1)
        )
        return None if row is None else self.load_lexical_index(row.id)

    def load_lexical_index(self, index_version_id: UUID) -> LexicalIndexResult:
        row = self._session.get(LexicalIndexVersion, index_version_id)
        if row is None:
            raise ValueError("lexical index not found")
        postings = self._session.scalars(
            select(LexicalPosting)
            .where(LexicalPosting.index_version_id == index_version_id)
            .order_by(LexicalPosting.token, LexicalPosting.chunk_id, LexicalPosting.field_kind)
        ).all()
        return LexicalIndexResult(
            status=IndexStatus(row.status),
            index_version_id=row.id,
            document_set_checksum=row.document_set_checksum,
            document_count=row.document_count,
            chunk_count=row.chunk_count,
            average_chunk_length=row.average_length,
            postings=tuple(
                LexicalPostingDraft(
                    token=posting.token,
                    chunk_id=posting.chunk_id,
                    term_frequency=posting.term_frequency,
                    field_kind=cast(Literal["BODY", "SECTION_TITLE"], posting.field_kind),
                    positions=tuple(posting.positions),
                )
                for posting in postings
            ),
            reused=True,
        )

    def find_run_by_fingerprint(self, fingerprint: str) -> RetrievalRunRecord | None:
        row = self._session.scalar(
            select(RetrievalRun).where(RetrievalRun.request_fingerprint == fingerprint)
        )
        return None if row is None else _run_record(row)

    def create_run(self, value: RetrievalRunWrite) -> RetrievalRunRecord:
        return self.acquire_run(value)[0]

    def acquire_run(self, value: RetrievalRunWrite) -> tuple[RetrievalRunRecord, bool]:
        existing = self.find_run_by_fingerprint(value.request_fingerprint)
        if existing is not None:
            return existing, False
        row = RetrievalRun(
            **value.model_dump(mode="python"),
            warnings=[],
            completed_at=None,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError:
            winner = self.find_run_by_fingerprint(value.request_fingerprint)
            if winner is None:
                raise
            return winner, False
        return _run_record(row), True

    def add_hits(self, run_id: UUID, hits: tuple[RetrievalHitWrite, ...]) -> None:
        self._session.add_all(
            RetrievalHit(retrieval_run_id=run_id, **hit.model_dump(mode="python")) for hit in hits
        )
        self._session.flush()

    def valid_citation_ids(
        self, citation_ids: tuple[UUID, ...], request: RetrievalRequest
    ) -> frozenset[UUID]:
        if self._blob_storage is None:
            return frozenset()
        return frozenset(
            citation_id
            for citation_id in citation_ids
            if (
                self.verify_citation(
                    citation_id,
                    snapshot_id=request.filters.snapshot_id,
                    research_as_of_time=request.filters.research_as_of_time,
                    strict_historical=request.filters.strict_unknown_publication,
                )
                or {}
            ).get("citation_status")
            == "VALID"
        )

    def finish_run(
        self,
        run_id: UUID,
        completion: RetrievalCompletion,
    ) -> RetrievalRunRecord:
        row = self._session.get(RetrievalRun, run_id)
        if row is None:
            raise ValueError("retrieval run not found")
        if row.completed_at is not None:
            raise ValueError("retrieval run is already terminal")
        row.status = completion.status.value
        row.warnings = list(completion.warnings)
        from sqlalchemy import func

        row.completed_at = self._session.scalar(select(func.now()))
        self._session.flush()
        return _run_record(row)

    def list_hits(self, run_id: UUID, limit: int) -> tuple[RetrievalHitRecord, ...]:
        rows = self._session.scalars(
            select(RetrievalHit)
            .where(RetrievalHit.retrieval_run_id == run_id)
            .order_by(RetrievalHit.final_rank, RetrievalHit.id)
            .limit(min(max(limit, 1), 20))
        ).all()
        return tuple(_hit_record(row) for row in rows)

    def find_bundle_for_request(
        self, request_basis_fingerprint: str, request: RetrievalRequest
    ) -> EvidenceBundle | None:
        statement = select(RetrievalRun).where(
            RetrievalRun.request_basis_fingerprint == request_basis_fingerprint,
            RetrievalRun.completed_at.is_not(None),
        )
        if request.mode != RetrievalMode.VECTOR:
            index_statement = select(LexicalIndexVersion.id).where(
                LexicalIndexVersion.security_id == request.filters.security_id,
                LexicalIndexVersion.status == IndexStatus.COMPLETE.value,
            )
            if request.filters.snapshot_id is not None:
                index_statement = index_statement.where(
                    LexicalIndexVersion.snapshot_id == request.filters.snapshot_id
                )
            else:
                index_statement = index_statement.where(
                    LexicalIndexVersion.snapshot_id.is_(None),
                    LexicalIndexVersion.index_as_of_time == request.filters.research_as_of_time,
                )
            current_index_id = self._session.scalar(
                index_statement.order_by(
                    LexicalIndexVersion.completed_at.desc(), LexicalIndexVersion.id
                ).limit(1)
            )
            if current_index_id is None:
                return None
            statement = statement.where(RetrievalRun.lexical_index_version_id == current_index_id)
        run = self._session.scalar(
            statement.order_by(RetrievalRun.completed_at.desc(), RetrievalRun.id).limit(1)
        )
        if run is None:
            return None
        return self._bundle_for_run(run)

    def list_document_versions(
        self,
        *,
        security_id: UUID,
        snapshot_id: UUID | None,
        research_as_of_time: datetime | None,
        limit: int,
    ) -> tuple[dict[str, object], ...]:
        statement = select(DocumentVersion).where(DocumentVersion.security_id == security_id)
        if snapshot_id is not None:
            statement = statement.join(
                SnapshotDocumentVersion,
                SnapshotDocumentVersion.document_version_id == DocumentVersion.id,
            ).where(SnapshotDocumentVersion.snapshot_id == snapshot_id)
        elif research_as_of_time is not None:
            statement = statement.where(
                DocumentVersion.published_at.is_not(None),
                DocumentVersion.published_at <= research_as_of_time,
            )
        rows = self._session.scalars(
            statement.order_by(
                DocumentVersion.published_at.desc().nulls_last(),
                DocumentVersion.version_number.desc(),
                DocumentVersion.id,
            ).limit(min(max(limit, 1), 20))
        ).all()
        return tuple(_document_metadata(row) for row in rows)

    def get_document_metadata(self, record_id: UUID) -> dict[str, object] | None:
        row = self._session.get(DocumentVersion, record_id)
        return None if row is None else _document_metadata(row)

    def get_document_chunk(self, record_id: UUID) -> dict[str, object] | None:
        row = self._session.get(DocumentChunk, record_id)
        if row is None:
            return None
        return {
            "chunk_id": row.id,
            "document_version_id": row.document_version_id,
            "parse_run_id": row.parse_run_id,
            "chunk_version": row.chunk_version,
            "chunk_index": row.chunk_index,
            "text": row.text,
            "language": row.language,
            "content_kind": row.content_kind,
            "locator_type": row.locator_type,
            "start_page": row.start_page,
            "end_page": row.end_page,
            "start_offset": row.start_offset,
            "end_offset": row.end_offset,
            "checksum": row.checksum,
            "warnings": tuple(row.warnings),
        }

    def get_citation(self, record_id: UUID) -> dict[str, object] | None:
        row = self._session.get(CitationAnchor, record_id)
        return None if row is None else _citation_metadata(row)

    def get_citation_context(self, citation_id: UUID) -> CitationContext | None:
        row = self._session.execute(
            select(CitationAnchor, DocumentVersion, DocumentParseRun, DocumentChunk)
            .join(DocumentVersion, DocumentVersion.id == CitationAnchor.document_version_id)
            .join(DocumentParseRun, DocumentParseRun.id == CitationAnchor.parse_run_id)
            .outerjoin(DocumentChunk, DocumentChunk.id == CitationAnchor.chunk_id)
            .where(CitationAnchor.id == citation_id)
        ).one_or_none()
        if row is None or self._blob_storage is None:
            return None
        citation, version, parse_run, chunk = row
        if parse_run.canonical_text is None:
            return None
        try:
            metadata = self._blob_storage.metadata(version.storage_uri)
            content = self._blob_storage.get(version.storage_uri)
        except BlobStorageError:
            return None
        pages = self._session.scalars(
            select(DocumentPage).where(DocumentPage.parse_run_id == parse_run.id)
        ).all()
        sections = self._session.scalars(
            select(DocumentSection).where(DocumentSection.parse_run_id == parse_run.id)
        ).all()
        snapshot_ids = tuple(
            self._session.scalars(
                select(SnapshotDocumentVersion.snapshot_id)
                .where(SnapshotDocumentVersion.document_version_id == version.id)
                .order_by(SnapshotDocumentVersion.snapshot_id)
            ).all()
        )
        superseder_id, superseded_at, supersession_time_unknown = self._supersession_state(
            version.id
        )
        locator = citation.locator
        return CitationContext(
            citation=CitationAnchorRecord(
                id=citation.id,
                document_version_id=citation.document_version_id,
                parse_run_id=citation.parse_run_id,
                page_id=citation.page_id,
                section_id=citation.section_id,
                chunk_id=citation.chunk_id,
                locator_type=LocatorType(citation.locator_type),
                start_page=_optional_int(locator.get("start_page")),
                end_page=_optional_int(locator.get("end_page")),
                html_anchor=_optional_str(locator.get("html_anchor")),
                json_pointer=_optional_str(locator.get("json_pointer")),
                start_offset=_optional_int(locator.get("start_offset")),
                end_offset=_optional_int(locator.get("end_offset")),
                excerpt=citation.excerpt,
                excerpt_checksum=citation.excerpt_checksum,
                canonical_text_checksum=citation.canonical_text_checksum,
                document_checksum=citation.document_checksum,
                locator_checksum=citation.locator_checksum,
                citation_version=citation.citation_version,
                parser_version=citation.parser_version,
                sanitizer_version=citation.sanitizer_version,
                created_at=citation.created_at,
            ),
            document_version=_document_version_record(version),
            canonical_source_text=parse_run.canonical_text,
            blob_bytes=content,
            blob_mime_type=metadata.content_type,
            blob_checksum=metadata.checksum_sha256,
            blob_size=metadata.size_bytes,
            snapshot_ids=snapshot_ids,
            superseded_by_document_version_id=superseder_id,
            superseded_at=superseded_at,
            supersession_time_unknown=supersession_time_unknown,
            available_page_numbers=tuple(sorted(page.page_number for page in pages)),
            page_texts={page.page_number: page.text for page in pages},
            available_section_ids=tuple(sorted((section.id for section in sections), key=str)),
            section_paths={section.id: section.section_path for section in sections},
            section_ranges={
                section.id: (section.start_offset, section.end_offset) for section in sections
            },
            available_html_anchors=tuple(
                sorted(
                    section.section_path
                    for section in sections
                    if section.locator_type == LocatorType.HTML_ANCHOR_RANGE.value
                )
            ),
            available_json_pointers=tuple(
                sorted(
                    section.section_path
                    for section in sections
                    if section.locator_type == LocatorType.JSON_POINTER.value
                )
            ),
            chunk_text=None if chunk is None else chunk.text,
            parser_version=parse_run.parser_version,
            sanitizer_version=parse_run.sanitizer_version,
        )

    def verify_citation(
        self,
        record_id: UUID,
        *,
        snapshot_id: UUID | None,
        research_as_of_time: datetime | None,
        strict_historical: bool,
    ) -> dict[str, object] | None:
        if self._session.get(CitationAnchor, record_id) is None:
            return None
        warnings: tuple[str, ...]
        if self._blob_storage is None:
            status = "BLOCKED"
            warnings = ("BLOB_VERIFICATION_REQUIRES_EXPLICIT_CONTEXT",)
        else:
            result = CitationVerifier(self, self._blob_storage).verify(
                record_id,
                CitationScope(
                    snapshot_id=snapshot_id,
                    research_as_of_time=research_as_of_time,
                    strict_historical=strict_historical,
                ),
            )
            status = result.status.value
            warnings = result.warnings
        return {
            "citation_id": record_id,
            "document_version_id": (
                None
                if (context := self.get_citation_context(record_id)) is None
                else context.document_version.id
            ),
            "citation_status": status,
            "warnings": warnings,
        }

    def _is_superseded_at(
        self, document_version_id: UUID, research_as_of_time: datetime | None
    ) -> bool:
        superseder_id, superseded_at, time_unknown = self._supersession_state(document_version_id)
        if superseder_id is None:
            return False
        if time_unknown or research_as_of_time is None:
            return True
        return superseded_at is None or superseded_at <= research_as_of_time

    def get_retrieval_run(self, record_id: UUID) -> dict[str, object] | None:
        row = self._session.get(RetrievalRun, record_id)
        if row is None or row.completed_at is None:
            return None
        return _run_record(row).model_dump(mode="python")

    def get_evidence_bundle(self, record_id: UUID) -> dict[str, object] | None:
        run = self._session.get(RetrievalRun, record_id)
        if run is None or run.completed_at is None:
            return None
        bundle = self._bundle_for_run(run)
        return bundle.model_dump(mode="python")

    def _bundle_for_run(self, run: RetrievalRun) -> EvidenceBundle:
        total_hits = int(
            self._session.scalar(
                select(func.count(RetrievalHit.id)).where(RetrievalHit.retrieval_run_id == run.id)
            )
            or 0
        )
        rows = self._session.execute(
            select(
                RetrievalHit,
                CitationAnchor,
                DocumentChunk,
                DocumentVersion,
                LogicalDocument,
                DocumentParseRun,
            )
            .join(CitationAnchor, CitationAnchor.id == RetrievalHit.citation_id)
            .join(DocumentChunk, DocumentChunk.id == RetrievalHit.chunk_id)
            .join(DocumentVersion, DocumentVersion.id == CitationAnchor.document_version_id)
            .join(LogicalDocument, LogicalDocument.id == DocumentVersion.logical_document_id)
            .join(DocumentParseRun, DocumentParseRun.id == CitationAnchor.parse_run_id)
            .where(RetrievalHit.retrieval_run_id == run.id)
            .order_by(RetrievalHit.final_rank, RetrievalHit.id)
            .limit(20)
        ).all()
        valid_rows = tuple(
            (hit, citation, chunk, version, logical, parse_run)
            for hit, citation, chunk, version, logical, parse_run in rows
            if (
                self.verify_citation(
                    citation.id,
                    snapshot_id=run.snapshot_id,
                    research_as_of_time=run.research_as_of_time,
                    strict_historical=True,
                )
                or {}
            ).get("citation_status")
            == "VALID"
        )
        excluded = len(valid_rows) != total_hits
        status = RetrievalStatus(run.status)
        if excluded and status == RetrievalStatus.PASS:
            status = RetrievalStatus.PARTIAL
        warnings = tuple(run.warnings) + (("INVALID_CITATIONS_EXCLUDED",) if excluded else ())
        return EvidenceBundle(
            status=status,
            retrieval_run_id=run.id,
            mode=RetrievalMode(run.mode),
            research_as_of_time=run.research_as_of_time,
            snapshot_id=run.snapshot_id,
            lexical_index_version_id=run.lexical_index_version_id,
            vector_index_version_id=run.vector_index_version_id,
            items=tuple(
                EvidenceItem(
                    citation_id=citation.id,
                    document_version_id=citation.document_version_id,
                    chunk_id=chunk.id,
                    excerpt=citation.excerpt,
                    document_type=logical.document_type,
                    trust_level=TrustLevel(version.trust_level),
                    published_at=version.published_at,
                    provider_id=version.provider_id,
                    source_document_id=version.source_document_id,
                    evidence_origin=cast(EvidenceOrigin, version.evidence_origin),
                    access_mode=cast(AccessMode, version.access_mode),
                    live_status=cast(LiveStatus, version.live_status),
                    locator_type=LocatorType(citation.locator_type),
                    start_page=_optional_int(citation.locator.get("start_page")),
                    end_page=_optional_int(citation.locator.get("end_page")),
                    section_path=_optional_str(citation.locator.get("section_path")),
                    chunk_version=chunk.chunk_version,
                    parser_version=parse_run.parser_version,
                    tokenizer_version=run.tokenizer_version,
                    citation_version=citation.citation_version,
                    document_checksum=version.checksum,
                    match_reason=hit.rerank_reason,
                )
                for hit, citation, chunk, version, logical, parse_run in valid_rows
            ),
            warnings=warnings,
        )


def _run_record(row: RetrievalRun) -> RetrievalRunRecord:
    return RetrievalRunRecord(
        id=row.id,
        request_fingerprint=row.request_fingerprint,
        request_basis_fingerprint=row.request_basis_fingerprint,
        security_id=row.security_id,
        snapshot_id=row.snapshot_id,
        research_as_of_time=row.research_as_of_time,
        mode=RetrievalMode(row.mode),
        original_query=row.original_query,
        normalized_query=row.normalized_query,
        max_results=row.max_results,
        tokenizer_version=row.tokenizer_version,
        lexical_index_version_id=row.lexical_index_version_id,
        vector_index_version_id=row.vector_index_version_id,
        fusion_version=row.fusion_version,
        reranker_version=row.reranker_version,
        status=RetrievalStatus(row.status),
        warnings=tuple(row.warnings),
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _hit_record(row: RetrievalHit) -> RetrievalHitRecord:
    return RetrievalHitRecord(
        id=row.id,
        retrieval_run_id=row.retrieval_run_id,
        chunk_id=row.chunk_id,
        citation_id=row.citation_id,
        final_rank=row.final_rank,
        lexical_rank=row.lexical_rank,
        vector_rank=row.vector_rank,
        fusion_score=row.fusion_score,
        rerank_reason=row.rerank_reason,
        created_at=row.created_at,
    )


def _document_metadata(row: DocumentVersion) -> dict[str, object]:
    return {
        "document_version_id": row.id,
        "logical_document_id": row.logical_document_id,
        "source_document_id": row.source_document_id,
        "security_id": row.security_id,
        "provider_id": row.provider_id,
        "version_number": row.version_number,
        "supersedes_document_version_id": row.supersedes_document_version_id,
        "mime_type": row.mime_type,
        "checksum": row.checksum,
        "byte_size": row.byte_size,
        "published_at": row.published_at,
        "filed_at": row.filed_at,
        "period_end": row.period_end,
        "retrieved_at": row.retrieved_at,
        "document_language": row.document_language,
        "trust_level": row.trust_level,
        "evidence_origin": row.evidence_origin,
        "access_mode": row.access_mode,
        "live_status": row.live_status,
        "source_version_status": row.source_version_status,
    }


def _citation_metadata(row: CitationAnchor) -> dict[str, object]:
    return {
        "citation_id": row.id,
        "document_version_id": row.document_version_id,
        "parse_run_id": row.parse_run_id,
        "page_id": row.page_id,
        "section_id": row.section_id,
        "chunk_id": row.chunk_id,
        "locator_type": row.locator_type,
        "locator": row.locator,
        "excerpt": row.excerpt,
        "excerpt_checksum": row.excerpt_checksum,
        "document_checksum": row.document_checksum,
        "locator_checksum": row.locator_checksum,
        "citation_version": row.citation_version,
        "parser_version": row.parser_version,
        "sanitizer_version": row.sanitizer_version,
    }


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _document_version_record(row: DocumentVersion) -> DocumentVersionRecord:
    return DocumentVersionRecord(
        id=row.id,
        logical_document_id=row.logical_document_id,
        source_document_id=row.source_document_id,
        security_id=row.security_id,
        provider_id=row.provider_id,
        source_payload_id=row.source_payload_id,
        version_number=row.version_number,
        supersedes_document_version_id=row.supersedes_document_version_id,
        storage_uri=row.storage_uri,
        mime_type=row.mime_type,
        checksum_algorithm="sha256",
        checksum=row.checksum,
        byte_size=row.byte_size,
        published_at=row.published_at,
        filed_at=row.filed_at,
        period_end=row.period_end,
        retrieved_at=row.retrieved_at,
        document_language=DocumentLanguage(row.document_language),
        trust_level=TrustLevel(row.trust_level),
        evidence_origin=cast(EvidenceOrigin, row.evidence_origin),
        access_mode=cast(AccessMode, row.access_mode),
        live_status=cast(LiveStatus, row.live_status),
        source_version_status=SourceVersionStatus(row.source_version_status),
        created_at=row.created_at,
    )


def _snapshot_version_record(row: SnapshotDocumentVersion) -> SnapshotDocumentVersionRecord:
    return SnapshotDocumentVersionRecord(
        snapshot_id=row.snapshot_id,
        document_version_id=row.document_version_id,
        snapshot_item_id=row.snapshot_item_id,
        created_at=row.created_at,
    )


def _parse_run_record(row: DocumentParseRun) -> DocumentParseRunRecord:
    return DocumentParseRunRecord(
        id=row.id,
        document_version_id=row.document_version_id,
        parser_name=row.parser_name,
        parser_version=row.parser_version,
        sanitizer_version=row.sanitizer_version,
        config_checksum=row.config_checksum,
        status=ParseStatus(row.status),
        canonical_text_checksum=row.canonical_text_checksum,
        warnings=tuple(row.warnings),
        started_at=row.started_at,
        completed_at=row.completed_at,
    )
