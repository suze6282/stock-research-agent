from __future__ import annotations

from sqlalchemy import Float

from stock_research_agent.db.base import Base
from stock_research_agent.db.models.knowledge import (  # noqa: F401
    CitationAnchor,
    DocumentChunk,
    DocumentPage,
    DocumentParseRun,
    DocumentSection,
    DocumentVersion,
    EmbeddingRecord,
    LexicalIndexVersion,
    LexicalPosting,
    LogicalDocument,
    RetrievalHit,
    RetrievalRun,
    SnapshotDocumentVersion,
    VectorIndexVersion,
)

TABLES = {
    "logical_documents",
    "document_versions",
    "snapshot_document_versions",
    "document_parse_runs",
    "document_pages",
    "document_sections",
    "document_chunks",
    "citation_anchors",
    "lexical_index_versions",
    "lexical_postings",
    "embedding_records",
    "vector_index_versions",
    "retrieval_runs",
    "retrieval_hits",
}


def test_stage6_declares_exact_fourteen_tables_without_float_or_vector_columns() -> None:
    assert TABLES <= set(Base.metadata.tables)
    for table_name in TABLES:
        table = Base.metadata.tables[table_name]
        assert table.primary_key.name == f"pk_{table_name}"
        assert not any(isinstance(column.type, Float) for column in table.columns)
        assert not any("vector" in str(column.type).casefold() for column in table.columns)


def test_stage6_foreign_keys_are_restrict_and_core_query_indexes_exist() -> None:
    for table_name in TABLES:
        for constraint in Base.metadata.tables[table_name].foreign_key_constraints:
            assert constraint.ondelete == "RESTRICT"
    expected = {
        "logical_documents": "ix_logical_documents_security_type",
        "document_versions": "ix_document_versions_security_published",
        "document_chunks": "ix_document_chunks_parse_run_index",
        "lexical_postings": "ix_lexical_postings_index_token",
        "retrieval_runs": "ix_retrieval_runs_security_scope",
        "retrieval_hits": "ix_retrieval_hits_run_rank",
    }
    for table_name, index_name in expected.items():
        assert index_name in {index.name for index in Base.metadata.tables[table_name].indexes}


def test_parse_run_persists_canonical_text_for_exact_reuse() -> None:
    columns = DocumentParseRun.__table__.columns
    assert "canonical_text" in columns
    assert columns["canonical_text"].type.__class__.__name__ == "Text"


def test_retrieval_hit_requires_a_citation_bound_to_the_same_chunk() -> None:
    hit_table = RetrievalHit.__table__
    assert hit_table.columns["citation_id"].nullable is False
    foreign_keys = {constraint.name: constraint for constraint in hit_table.foreign_key_constraints}
    constraint = foreign_keys["fk_retrieval_hits_citation_chunk"]
    assert tuple(constraint.column_keys) == ("citation_id", "chunk_id")


def test_citation_anchor_has_native_page_and_section_foreign_keys() -> None:
    foreign_keys = {
        constraint.name: constraint
        for constraint in CitationAnchor.__table__.foreign_key_constraints
    }
    assert "fk_citation_anchors_page" in foreign_keys
    assert "fk_citation_anchors_section" in foreign_keys
