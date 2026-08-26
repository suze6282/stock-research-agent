"""SQLAlchemy models for immutable document evidence and retrieval history."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from stock_research_agent.db.base import Base


class _CreatedUuidMixin:
    id: Mapped[UUID] = mapped_column(Uuid, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LogicalDocument(_CreatedUuidMixin, Base):
    __tablename__ = "logical_documents"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_logical_documents"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_logical_documents_security",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "security_id",
            "identity_scheme",
            "normalized_identity_value",
            name="uq_logical_documents_identity",
        ),
        CheckConstraint(
            "length(identity_scheme) BETWEEN 1 AND 64", name="ck_logical_documents_scheme"
        ),
        Index("ix_logical_documents_security_type", "security_id", "document_type"),
    )
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    form_type: Mapped[str | None] = mapped_column(String(64))
    identity_scheme: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_value: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_identity_value: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)


class DocumentVersion(_CreatedUuidMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_document_versions"),
        ForeignKeyConstraint(
            ["logical_document_id"],
            ["logical_documents.id"],
            name="fk_document_versions_logical",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name="fk_document_versions_source_document",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_document_versions_security",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_document_versions_provider",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_payload_id"],
            ["raw_payloads.id"],
            name="fk_document_versions_payload",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supersedes_document_version_id"],
            ["document_versions.id"],
            name="fk_document_versions_supersedes",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "logical_document_id", "version_number", name="uq_document_versions_number"
        ),
        UniqueConstraint("logical_document_id", "checksum", name="uq_document_versions_checksum"),
        CheckConstraint("version_number > 0", name="ck_document_versions_number"),
        CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="ck_document_versions_checksum"),
        CheckConstraint("byte_size BETWEEN 1 AND 26214400", name="ck_document_versions_size"),
        CheckConstraint("checksum_algorithm = 'sha256'", name="ck_document_versions_algorithm"),
        CheckConstraint(
            "source_version_status IN ('ACTIVE','WITHDRAWN','UNKNOWN')",
            name="ck_document_versions_status",
        ),
        Index("ix_document_versions_security_published", "security_id", "published_at"),
    )
    logical_document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_payload_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_document_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    storage_uri: Mapped[str] = mapped_column(String(256), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    checksum_algorithm: Mapped[str] = mapped_column(String(16), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    published_at: Mapped[datetime | None]
    filed_at: Mapped[datetime | None]
    period_end: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(nullable=False)
    document_language: Mapped[str] = mapped_column(String(16), nullable=False)
    trust_level: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_origin: Mapped[str] = mapped_column(String(32), nullable=False)
    access_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    live_status: Mapped[str] = mapped_column(String(16), nullable=False)
    source_version_status: Mapped[str] = mapped_column(String(16), nullable=False)


class SnapshotDocumentVersion(Base):
    __tablename__ = "snapshot_document_versions"
    __table_args__ = (
        PrimaryKeyConstraint(
            "snapshot_id", "document_version_id", name="pk_snapshot_document_versions"
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_snapshot_document_versions_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_snapshot_document_versions_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_item_id"],
            ["snapshot_items.id"],
            name="fk_snapshot_document_versions_item",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("snapshot_item_id", name="uq_snapshot_document_versions_item"),
    )
    snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_item_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DocumentParseRun(_CreatedUuidMixin, Base):
    __tablename__ = "document_parse_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_document_parse_runs"),
        ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_document_parse_runs_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "document_version_id",
            "parser_name",
            "parser_version",
            "sanitizer_version",
            "config_checksum",
            name="uq_document_parse_runs_generation",
        ),
        CheckConstraint(
            "status IN ('RUNNING','PASS','PARTIAL','BLOCKED','FAIL')",
            name="ck_document_parse_runs_status",
        ),
        Index("ix_document_parse_runs_version_status", "document_version_id", "status"),
    )
    document_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    parser_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    sanitizer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    config_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_text: Mapped[str | None] = mapped_column(Text)
    canonical_text_checksum: Mapped[str | None] = mapped_column(String(64))
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None]


class DocumentPage(_CreatedUuidMixin, Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_document_pages"),
        ForeignKeyConstraint(
            ["parse_run_id"],
            ["document_parse_runs.id"],
            name="fk_document_pages_run",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("parse_run_id", "page_number", name="uq_document_pages_number"),
        CheckConstraint("page_number > 0 AND character_count >= 0", name="ck_document_pages_range"),
    )
    parse_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class DocumentSection(_CreatedUuidMixin, Base):
    __tablename__ = "document_sections"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_document_sections"),
        ForeignKeyConstraint(
            ["parse_run_id"],
            ["document_parse_runs.id"],
            name="fk_document_sections_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["parent_section_id"],
            ["document_sections.id"],
            name="fk_document_sections_parent",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("parse_run_id", "section_path", name="uq_document_sections_path"),
        CheckConstraint("level BETWEEN 1 AND 64", name="ck_document_sections_level"),
        CheckConstraint(
            "start_offset IS NULL OR end_offset > start_offset", name="ck_document_sections_offsets"
        ),
    )
    parse_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    parent_section_id: Mapped[UUID | None] = mapped_column(Uuid)
    section_path: Mapped[str] = mapped_column(String(512), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    locator_type: Mapped[str] = mapped_column(String(32), nullable=False)
    start_page: Mapped[int | None] = mapped_column(Integer)
    end_page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    text_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    content_kind: Mapped[str] = mapped_column(String(16), nullable=False)


class DocumentChunk(_CreatedUuidMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_document_chunks"),
        ForeignKeyConstraint(
            ["parse_run_id"],
            ["document_parse_runs.id"],
            name="fk_document_chunks_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_document_chunks_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "parse_run_id",
            "chunk_version",
            "chunk_index",
            name="uq_document_chunks_generation_index",
        ),
        UniqueConstraint("parse_run_id", "checksum", name="uq_document_chunks_checksum"),
        CheckConstraint("chunk_index >= 0 AND token_count >= 0", name="ck_document_chunks_counts"),
        CheckConstraint(
            "start_offset IS NULL OR end_offset > start_offset", name="ck_document_chunks_offsets"
        ),
        Index("ix_document_chunks_parse_run_index", "parse_run_id", "chunk_index"),
    )
    parse_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    chunk_version: Mapped[str] = mapped_column(String(32), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    content_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    locator_type: Mapped[str] = mapped_column(String(32), nullable=False)
    start_page: Mapped[int | None] = mapped_column(Integer)
    end_page: Mapped[int | None] = mapped_column(Integer)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class CitationAnchor(_CreatedUuidMixin, Base):
    __tablename__ = "citation_anchors"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_citation_anchors"),
        ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_citation_anchors_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["parse_run_id"],
            ["document_parse_runs.id"],
            name="fk_citation_anchors_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_citation_anchors_chunk",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["page_id"],
            ["document_pages.id"],
            name="fk_citation_anchors_page",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["section_id"],
            ["document_sections.id"],
            name="fk_citation_anchors_section",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "chunk_id", name="uq_citation_anchors_id_chunk"),
        UniqueConstraint(
            "document_version_id",
            "parse_run_id",
            "locator_checksum",
            name="uq_citation_anchors_locator",
        ),
        CheckConstraint("length(excerpt) BETWEEN 1 AND 1000", name="ck_citation_anchors_excerpt"),
        CheckConstraint(
            "(locator_type = 'PDF_PAGE_RANGE' AND page_id IS NOT NULL) OR "
            "(locator_type IN ('HTML_ANCHOR_RANGE','JSON_POINTER','SECTION_RANGE') "
            "AND section_id IS NOT NULL) OR locator_type = 'TEXT_OFFSET_RANGE'",
            name="ck_citation_anchors_native_locator",
        ),
    )
    document_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    parse_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    page_id: Mapped[UUID | None] = mapped_column(Uuid)
    section_id: Mapped[UUID | None] = mapped_column(Uuid)
    chunk_id: Mapped[UUID | None] = mapped_column(Uuid)
    locator_type: Mapped[str] = mapped_column(String(32), nullable=False)
    locator: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_text_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    document_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    locator_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    citation_version: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    sanitizer_version: Mapped[str] = mapped_column(String(64), nullable=False)


class LexicalIndexVersion(_CreatedUuidMixin, Base):
    __tablename__ = "lexical_index_versions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_lexical_index_versions"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_lexical_index_versions_security",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_lexical_index_versions_snapshot",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("fingerprint", name="uq_lexical_index_versions_fingerprint"),
        CheckConstraint(
            "(snapshot_id IS NULL) <> (index_as_of_time IS NULL)",
            name="ck_lexical_index_versions_scope",
        ),
        CheckConstraint(
            "status IN ('BUILDING','COMPLETE','PARTIAL','BLOCKED','FAILED')",
            name="ck_lexical_index_versions_status",
        ),
        Index(
            "ix_lexical_index_versions_security_scope",
            "security_id",
            "snapshot_id",
            "index_as_of_time",
        ),
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID | None] = mapped_column(Uuid)
    index_as_of_time: Mapped[datetime | None]
    tokenizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    chunk_version: Mapped[str] = mapped_column(String(32), nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    document_set_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    average_length: Mapped[Decimal] = mapped_column(Numeric(38, 12), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    completed_at: Mapped[datetime | None]


class LexicalPosting(_CreatedUuidMixin, Base):
    __tablename__ = "lexical_postings"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_lexical_postings"),
        ForeignKeyConstraint(
            ["index_version_id"],
            ["lexical_index_versions.id"],
            name="fk_lexical_postings_index",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_lexical_postings_chunk",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "index_version_id",
            "token",
            "chunk_id",
            "field_kind",
            name="uq_lexical_postings_identity",
        ),
        CheckConstraint("term_frequency > 0", name="ck_lexical_postings_tf"),
        Index("ix_lexical_postings_index_token", "index_version_id", "token"),
    )
    index_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    token: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    term_frequency: Mapped[int] = mapped_column(Integer, nullable=False)
    field_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    positions: Mapped[list[int]] = mapped_column(JSONB, nullable=False)


class EmbeddingRecord(_CreatedUuidMixin, Base):
    __tablename__ = "embedding_records"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_embedding_records"),
        ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_embedding_records_chunk",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "chunk_id", "provider", "model", "version", name="uq_embedding_records_generation"
        ),
        CheckConstraint("dimensions > 0", name="ck_embedding_records_dimensions"),
    )
    chunk_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    chunk_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    backend_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)


class VectorIndexVersion(_CreatedUuidMixin, Base):
    __tablename__ = "vector_index_versions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_vector_index_versions"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_vector_index_versions_security",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("fingerprint", name="uq_vector_index_versions_fingerprint"),
        CheckConstraint(
            "status IN ('BUILDING','COMPLETE','PARTIAL','BLOCKED','FAILED')",
            name="ck_vector_index_versions_status",
        ),
    )
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    backend: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    completed_at: Mapped[datetime | None]


class RetrievalRun(_CreatedUuidMixin, Base):
    __tablename__ = "retrieval_runs"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_retrieval_runs"),
        ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_retrieval_runs_security",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_retrieval_runs_snapshot",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["lexical_index_version_id"],
            ["lexical_index_versions.id"],
            name="fk_retrieval_runs_lexical_index",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["vector_index_version_id"],
            ["vector_index_versions.id"],
            name="fk_retrieval_runs_vector_index",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("request_fingerprint", name="uq_retrieval_runs_fingerprint"),
        CheckConstraint(
            "(snapshot_id IS NULL) <> (research_as_of_time IS NULL)", name="ck_retrieval_runs_scope"
        ),
        CheckConstraint(
            "status IN ('PASS','PARTIAL','BLOCKED','FAIL')", name="ck_retrieval_runs_status"
        ),
        CheckConstraint("max_results BETWEEN 1 AND 20", name="ck_retrieval_runs_max_results"),
        Index(
            "ix_retrieval_runs_security_scope", "security_id", "snapshot_id", "research_as_of_time"
        ),
        Index("ix_retrieval_runs_request_basis", "request_basis_fingerprint", "completed_at"),
    )
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_basis_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    security_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot_id: Mapped[UUID | None] = mapped_column(Uuid)
    research_as_of_time: Mapped[datetime | None]
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    original_query: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_query: Mapped[str] = mapped_column(String(256), nullable=False)
    max_results: Mapped[int] = mapped_column(Integer, nullable=False)
    tokenizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    lexical_index_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    vector_index_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    fusion_version: Mapped[str] = mapped_column(String(32), nullable=False)
    reranker_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    completed_at: Mapped[datetime | None]


class RetrievalHit(_CreatedUuidMixin, Base):
    __tablename__ = "retrieval_hits"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_retrieval_hits"),
        ForeignKeyConstraint(
            ["retrieval_run_id"],
            ["retrieval_runs.id"],
            name="fk_retrieval_hits_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_retrieval_hits_chunk",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["citation_id", "chunk_id"],
            ["citation_anchors.id", "citation_anchors.chunk_id"],
            name="fk_retrieval_hits_citation_chunk",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("retrieval_run_id", "final_rank", name="uq_retrieval_hits_rank"),
        UniqueConstraint("retrieval_run_id", "chunk_id", name="uq_retrieval_hits_chunk"),
        CheckConstraint("final_rank BETWEEN 1 AND 20", name="ck_retrieval_hits_rank"),
        Index("ix_retrieval_hits_run_rank", "retrieval_run_id", "final_rank"),
    )
    retrieval_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    chunk_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    citation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    final_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    lexical_rank: Mapped[int | None] = mapped_column(Integer)
    vector_rank: Mapped[int | None] = mapped_column(Integer)
    fusion_score: Mapped[Decimal] = mapped_column(Numeric(38, 12), nullable=False)
    rerank_reason: Mapped[str] = mapped_column(String(64), nullable=False)
