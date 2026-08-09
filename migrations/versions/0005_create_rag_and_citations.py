"""create rag and citations

Revision ID: 0005_rag_citations
Revises: 0004_financial_normalization
Create Date: 2026-07-20 20:55:54.991037
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_rag_citations"
down_revision: str | Sequence[str] | None = "0004_financial_normalization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_immutability_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION validate_document_version_lineage()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            logical_security_id uuid;
            source_security_id uuid;
            source_provider_id uuid;
            expected_source_payload_id uuid;
        BEGIN
            SELECT security_id INTO logical_security_id
              FROM logical_documents WHERE id = NEW.logical_document_id;
            SELECT source.security_id, source.provider_id, source.source_payload_id
              INTO source_security_id, source_provider_id, expected_source_payload_id
              FROM source_documents source WHERE source.id = NEW.source_document_id;
            IF logical_security_id IS NULL OR source_security_id IS NULL THEN
                RAISE EXCEPTION 'document version lineage source is missing'
                    USING ERRCODE = '23503';
            END IF;
            IF logical_security_id IS DISTINCT FROM NEW.security_id
               OR source_security_id IS DISTINCT FROM NEW.security_id
               OR source_provider_id IS DISTINCT FROM NEW.provider_id
               OR expected_source_payload_id IS DISTINCT FROM NEW.source_payload_id THEN
                RAISE EXCEPTION 'document version lineage identities do not match'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_versions_validate_lineage
        BEFORE INSERT ON document_versions
        FOR EACH ROW EXECUTE FUNCTION validate_document_version_lineage()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_document_version_supersession()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            superseded_logical_document_id uuid;
            superseded_version_number integer;
        BEGIN
            IF NEW.supersedes_document_version_id IS NULL THEN
                RETURN NEW;
            END IF;
            SELECT logical_document_id, version_number
              INTO superseded_logical_document_id, superseded_version_number
              FROM document_versions
             WHERE id = NEW.supersedes_document_version_id;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'superseded document version does not exist'
                    USING ERRCODE = '23503';
            END IF;
            IF superseded_logical_document_id <> NEW.logical_document_id THEN
                RAISE EXCEPTION 'superseded version must belong to the same logical document'
                    USING ERRCODE = '23514';
            END IF;
            IF superseded_version_number >= NEW.version_number THEN
                RAISE EXCEPTION 'superseded version must be older than the new version'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_versions_validate_supersession
        BEFORE INSERT ON document_versions
        FOR EACH ROW EXECUTE FUNCTION validate_document_version_supersession()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_citation_anchor_lineage()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            linked_parse_run_id uuid;
            linked_document_version_id uuid;
        BEGIN
            IF NEW.page_id IS NOT NULL THEN
                SELECT parse_run_id INTO linked_parse_run_id
                  FROM document_pages WHERE id = NEW.page_id;
                IF linked_parse_run_id IS DISTINCT FROM NEW.parse_run_id THEN
                    RAISE EXCEPTION 'citation page must belong to the cited parse run'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            IF NEW.section_id IS NOT NULL THEN
                SELECT parse_run_id INTO linked_parse_run_id
                  FROM document_sections WHERE id = NEW.section_id;
                IF linked_parse_run_id IS DISTINCT FROM NEW.parse_run_id THEN
                    RAISE EXCEPTION 'citation section must belong to the cited parse run'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            IF NEW.chunk_id IS NOT NULL THEN
                SELECT parse_run_id, document_version_id
                  INTO linked_parse_run_id, linked_document_version_id
                  FROM document_chunks WHERE id = NEW.chunk_id;
                IF linked_parse_run_id IS DISTINCT FROM NEW.parse_run_id
                   OR linked_document_version_id IS DISTINCT FROM NEW.document_version_id THEN
                    RAISE EXCEPTION 'citation chunk must belong to the cited generation'
                        USING ERRCODE = '23514';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_citation_anchors_validate_lineage
        BEFORE INSERT ON citation_anchors
        FOR EACH ROW EXECUTE FUNCTION validate_citation_anchor_lineage()
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_stage6_evidence_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'immutable Stage 6 evidence cannot be modified'
                USING ERRCODE = '23514';
        END;
        $$
        """
    )
    for table_name in (
        "document_versions",
        "snapshot_document_versions",
        "citation_anchors",
        "document_pages",
        "document_sections",
        "document_chunks",
        "lexical_postings",
        "embedding_records",
        "retrieval_hits",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION prevent_stage6_evidence_mutation()
            """
        )
    op.execute(
        """
        CREATE FUNCTION prevent_document_section_cycles()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            parent_run_id uuid;
        BEGIN
            IF NEW.parent_section_id IS NULL THEN
                RETURN NEW;
            END IF;
            IF NEW.parent_section_id = NEW.id THEN
                RAISE EXCEPTION 'document section cannot parent itself'
                    USING ERRCODE = '23514';
            END IF;
            SELECT parse_run_id INTO parent_run_id
              FROM document_sections WHERE id = NEW.parent_section_id;
            IF parent_run_id IS NULL OR parent_run_id <> NEW.parse_run_id THEN
                RAISE EXCEPTION 'document section parent must belong to the same parse run'
                    USING ERRCODE = '23514';
            END IF;
            IF EXISTS (
                WITH RECURSIVE ancestors(id, parent_section_id) AS (
                    SELECT id, parent_section_id FROM document_sections
                     WHERE id = NEW.parent_section_id
                    UNION ALL
                    SELECT section.id, section.parent_section_id
                      FROM document_sections section
                      JOIN ancestors ON section.id = ancestors.parent_section_id
                )
                SELECT 1 FROM ancestors WHERE id = NEW.id
            ) THEN
                RAISE EXCEPTION 'document section parent cycle is not allowed'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_document_sections_no_cycles
        AFTER INSERT OR UPDATE OF parent_section_id, parse_run_id ON document_sections
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION prevent_document_section_cycles()
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_completed_stage6_run_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.completed_at IS NOT NULL THEN
                RAISE EXCEPTION 'completed Stage 6 run is immutable'
                    USING ERRCODE = '23514';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table_name in (
        "document_parse_runs",
        "lexical_index_versions",
        "vector_index_versions",
        "retrieval_runs",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_completed_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION prevent_completed_stage6_run_mutation()
            """
        )


def _drop_immutability_guards() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_citation_anchors_validate_lineage ON citation_anchors")
    op.execute("DROP TRIGGER IF EXISTS trg_document_versions_validate_lineage ON document_versions")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_document_versions_validate_supersession ON document_versions"
    )
    op.execute("DROP TRIGGER IF EXISTS trg_document_sections_no_cycles ON document_sections")
    for table_name in (
        "document_parse_runs",
        "lexical_index_versions",
        "vector_index_versions",
        "retrieval_runs",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_completed_immutable ON {table_name}")
    for table_name in (
        "document_versions",
        "snapshot_document_versions",
        "citation_anchors",
        "document_pages",
        "document_sections",
        "document_chunks",
        "lexical_postings",
        "embedding_records",
        "retrieval_hits",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS prevent_completed_stage6_run_mutation()")
    op.execute("DROP FUNCTION IF EXISTS prevent_stage6_evidence_mutation()")
    op.execute("DROP FUNCTION IF EXISTS prevent_document_section_cycles()")
    op.execute("DROP FUNCTION IF EXISTS validate_document_version_supersession()")
    op.execute("DROP FUNCTION IF EXISTS validate_document_version_lineage()")
    op.execute("DROP FUNCTION IF EXISTS validate_citation_anchor_lineage()")


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "logical_documents",
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("form_type", sa.String(length=64), nullable=True),
        sa.Column("identity_scheme", sa.String(length=64), nullable=False),
        sa.Column("identity_value", sa.String(length=256), nullable=False),
        sa.Column("normalized_identity_value", sa.String(length=256), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(identity_scheme) BETWEEN 1 AND 64", name="ck_logical_documents_scheme"
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_logical_documents_security",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_logical_documents"),
        sa.UniqueConstraint(
            "security_id",
            "identity_scheme",
            "normalized_identity_value",
            name="uq_logical_documents_identity",
        ),
    )
    op.create_index(
        "ix_logical_documents_security_type",
        "logical_documents",
        ["security_id", "document_type"],
        unique=False,
    )
    op.create_table(
        "vector_index_versions",
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("backend", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("chunk_version", sa.String(length=32), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('BUILDING','COMPLETE','PARTIAL','BLOCKED','FAILED')",
            name="ck_vector_index_versions_status",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_vector_index_versions_security",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vector_index_versions"),
        sa.UniqueConstraint("fingerprint", name="uq_vector_index_versions_fingerprint"),
    )
    op.create_table(
        "lexical_index_versions",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("index_as_of_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tokenizer_version", sa.String(length=32), nullable=False),
        sa.Column("chunk_version", sa.String(length=32), nullable=False),
        sa.Column("scoring_version", sa.String(length=32), nullable=False),
        sa.Column("document_set_checksum", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("average_length", sa.Numeric(precision=38, scale=12), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('BUILDING','COMPLETE','PARTIAL','BLOCKED','FAILED')",
            name="ck_lexical_index_versions_status",
        ),
        sa.CheckConstraint(
            "(snapshot_id IS NULL) <> (index_as_of_time IS NULL)",
            name="ck_lexical_index_versions_scope",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_lexical_index_versions_security",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_lexical_index_versions_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lexical_index_versions"),
        sa.UniqueConstraint("fingerprint", name="uq_lexical_index_versions_fingerprint"),
    )
    op.create_index(
        "ix_lexical_index_versions_security_scope",
        "lexical_index_versions",
        ["security_id", "snapshot_id", "index_as_of_time"],
        unique=False,
    )
    op.create_table(
        "retrieval_runs",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("request_basis_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("research_as_of_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("original_query", sa.String(length=256), nullable=False),
        sa.Column("normalized_query", sa.String(length=256), nullable=False),
        sa.Column("max_results", sa.Integer(), nullable=False),
        sa.Column("tokenizer_version", sa.String(length=32), nullable=False),
        sa.Column("lexical_index_version_id", sa.Uuid(), nullable=True),
        sa.Column("vector_index_version_id", sa.Uuid(), nullable=True),
        sa.Column("fusion_version", sa.String(length=32), nullable=False),
        sa.Column("reranker_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('PASS','PARTIAL','BLOCKED','FAIL')", name="ck_retrieval_runs_status"
        ),
        sa.CheckConstraint("max_results BETWEEN 1 AND 20", name="ck_retrieval_runs_max_results"),
        sa.CheckConstraint(
            "(snapshot_id IS NULL) <> (research_as_of_time IS NULL)", name="ck_retrieval_runs_scope"
        ),
        sa.ForeignKeyConstraint(
            ["lexical_index_version_id"],
            ["lexical_index_versions.id"],
            name="fk_retrieval_runs_lexical_index",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_retrieval_runs_security",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_retrieval_runs_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vector_index_version_id"],
            ["vector_index_versions.id"],
            name="fk_retrieval_runs_vector_index",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_retrieval_runs"),
        sa.UniqueConstraint("request_fingerprint", name="uq_retrieval_runs_fingerprint"),
    )
    op.create_index(
        "ix_retrieval_runs_security_scope",
        "retrieval_runs",
        ["security_id", "snapshot_id", "research_as_of_time"],
        unique=False,
    )
    op.create_index(
        "ix_retrieval_runs_request_basis",
        "retrieval_runs",
        ["request_basis_fingerprint", "completed_at"],
        unique=False,
    )
    op.create_table(
        "document_versions",
        sa.Column("logical_document_id", sa.Uuid(), nullable=False),
        sa.Column("source_document_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("source_payload_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("supersedes_document_version_id", sa.Uuid(), nullable=True),
        sa.Column("storage_uri", sa.String(length=256), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("checksum_algorithm", sa.String(length=16), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_language", sa.String(length=16), nullable=False),
        sa.Column("trust_level", sa.String(length=32), nullable=False),
        sa.Column("evidence_origin", sa.String(length=32), nullable=False),
        sa.Column("access_mode", sa.String(length=16), nullable=False),
        sa.Column("live_status", sa.String(length=16), nullable=False),
        sa.Column("source_version_status", sa.String(length=16), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="ck_document_versions_checksum"),
        sa.CheckConstraint("checksum_algorithm = 'sha256'", name="ck_document_versions_algorithm"),
        sa.CheckConstraint(
            "source_version_status IN ('ACTIVE','WITHDRAWN','UNKNOWN')",
            name="ck_document_versions_status",
        ),
        sa.CheckConstraint("byte_size BETWEEN 1 AND 10000000", name="ck_document_versions_size"),
        sa.CheckConstraint("version_number > 0", name="ck_document_versions_number"),
        sa.ForeignKeyConstraint(
            ["logical_document_id"],
            ["logical_documents.id"],
            name="fk_document_versions_logical",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["data_providers.id"],
            name="fk_document_versions_provider",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_document_versions_security",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name="fk_document_versions_source_document",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_payload_id"],
            ["raw_payloads.id"],
            name="fk_document_versions_payload",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_document_version_id"],
            ["document_versions.id"],
            name="fk_document_versions_supersedes",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.UniqueConstraint(
            "logical_document_id", "checksum", name="uq_document_versions_checksum"
        ),
        sa.UniqueConstraint(
            "logical_document_id", "version_number", name="uq_document_versions_number"
        ),
    )
    op.create_index(
        "ix_document_versions_security_published",
        "document_versions",
        ["security_id", "published_at"],
        unique=False,
    )
    op.create_table(
        "document_parse_runs",
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("parser_name", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("sanitizer_version", sa.String(length=64), nullable=False),
        sa.Column("config_checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=True),
        sa.Column("canonical_text_checksum", sa.String(length=64), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING','PASS','PARTIAL','BLOCKED','FAIL')",
            name="ck_document_parse_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_document_parse_runs_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_parse_runs"),
        sa.UniqueConstraint(
            "document_version_id",
            "parser_name",
            "parser_version",
            "sanitizer_version",
            "config_checksum",
            name="uq_document_parse_runs_generation",
        ),
    )
    op.create_index(
        "ix_document_parse_runs_version_status",
        "document_parse_runs",
        ["document_version_id", "status"],
        unique=False,
    )
    op.create_table(
        "snapshot_document_versions",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_item_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_snapshot_document_versions_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["data_snapshots.id"],
            name="fk_snapshot_document_versions_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_item_id"],
            ["snapshot_items.id"],
            name="fk_snapshot_document_versions_item",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_id", "document_version_id", name="pk_snapshot_document_versions"
        ),
        sa.UniqueConstraint("snapshot_item_id", name="uq_snapshot_document_versions_item"),
    )
    op.create_table(
        "document_chunks",
        sa.Column("parse_run_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_version", sa.String(length=32), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("content_kind", sa.String(length=16), nullable=False),
        sa.Column("locator_type", sa.String(length=32), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=True),
        sa.Column("end_page", sa.Integer(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chunk_index >= 0 AND token_count >= 0", name="ck_document_chunks_counts"
        ),
        sa.CheckConstraint(
            "start_offset IS NULL OR end_offset > start_offset", name="ck_document_chunks_offsets"
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_document_chunks_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parse_run_id"],
            ["document_parse_runs.id"],
            name="fk_document_chunks_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.UniqueConstraint("parse_run_id", "checksum", name="uq_document_chunks_checksum"),
        sa.UniqueConstraint(
            "parse_run_id",
            "chunk_version",
            "chunk_index",
            name="uq_document_chunks_generation_index",
        ),
    )
    op.create_index(
        "ix_document_chunks_parse_run_index",
        "document_chunks",
        ["parse_run_id", "chunk_index"],
        unique=False,
    )
    op.create_table(
        "document_pages",
        sa.Column("parse_run_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_checksum", sa.String(length=64), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "page_number > 0 AND character_count >= 0", name="ck_document_pages_range"
        ),
        sa.ForeignKeyConstraint(
            ["parse_run_id"],
            ["document_parse_runs.id"],
            name="fk_document_pages_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_pages"),
        sa.UniqueConstraint("parse_run_id", "page_number", name="uq_document_pages_number"),
    )
    op.create_table(
        "document_sections",
        sa.Column("parse_run_id", sa.Uuid(), nullable=False),
        sa.Column("parent_section_id", sa.Uuid(), nullable=True),
        sa.Column("section_path", sa.String(length=512), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("locator_type", sa.String(length=32), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=True),
        sa.Column("end_page", sa.Integer(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("text_checksum", sa.String(length=64), nullable=False),
        sa.Column("content_kind", sa.String(length=16), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("level BETWEEN 1 AND 64", name="ck_document_sections_level"),
        sa.CheckConstraint(
            "start_offset IS NULL OR end_offset > start_offset", name="ck_document_sections_offsets"
        ),
        sa.ForeignKeyConstraint(
            ["parent_section_id"],
            ["document_sections.id"],
            name="fk_document_sections_parent",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parse_run_id"],
            ["document_parse_runs.id"],
            name="fk_document_sections_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_sections"),
        sa.UniqueConstraint("parse_run_id", "section_path", name="uq_document_sections_path"),
    )
    op.create_table(
        "citation_anchors",
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("parse_run_id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=True),
        sa.Column("section_id", sa.Uuid(), nullable=True),
        sa.Column("chunk_id", sa.Uuid(), nullable=True),
        sa.Column("locator_type", sa.String(length=32), nullable=False),
        sa.Column("locator", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("excerpt_checksum", sa.String(length=64), nullable=False),
        sa.Column("canonical_text_checksum", sa.String(length=64), nullable=False),
        sa.Column("document_checksum", sa.String(length=64), nullable=False),
        sa.Column("locator_checksum", sa.String(length=64), nullable=False),
        sa.Column("citation_version", sa.String(length=32), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("sanitizer_version", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(excerpt) BETWEEN 1 AND 1000", name="ck_citation_anchors_excerpt"
        ),
        sa.CheckConstraint(
            "(locator_type = 'PDF_PAGE_RANGE' AND page_id IS NOT NULL) OR "
            "(locator_type IN ('HTML_ANCHOR_RANGE','JSON_POINTER','SECTION_RANGE') "
            "AND section_id IS NOT NULL) OR locator_type = 'TEXT_OFFSET_RANGE'",
            name="ck_citation_anchors_native_locator",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_citation_anchors_chunk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_citation_anchors_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parse_run_id"],
            ["document_parse_runs.id"],
            name="fk_citation_anchors_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["document_pages.id"],
            name="fk_citation_anchors_page",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["document_sections.id"],
            name="fk_citation_anchors_section",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_citation_anchors"),
        sa.UniqueConstraint(
            "document_version_id",
            "parse_run_id",
            "locator_checksum",
            name="uq_citation_anchors_locator",
        ),
        sa.UniqueConstraint("id", "chunk_id", name="uq_citation_anchors_id_chunk"),
    )
    op.create_table(
        "embedding_records",
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_checksum", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_checksum", sa.String(length=64), nullable=False),
        sa.Column("backend_reference", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("dimensions > 0", name="ck_embedding_records_dimensions"),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_embedding_records_chunk",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_embedding_records"),
        sa.UniqueConstraint(
            "chunk_id", "provider", "model", "version", name="uq_embedding_records_generation"
        ),
    )
    op.create_table(
        "lexical_postings",
        sa.Column("index_version_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("term_frequency", sa.Integer(), nullable=False),
        sa.Column("field_kind", sa.String(length=16), nullable=False),
        sa.Column("positions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("term_frequency > 0", name="ck_lexical_postings_tf"),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_lexical_postings_chunk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["index_version_id"],
            ["lexical_index_versions.id"],
            name="fk_lexical_postings_index",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lexical_postings"),
        sa.UniqueConstraint(
            "index_version_id",
            "token",
            "chunk_id",
            "field_kind",
            name="uq_lexical_postings_identity",
        ),
    )
    op.create_index(
        "ix_lexical_postings_index_token",
        "lexical_postings",
        ["index_version_id", "token"],
        unique=False,
    )
    op.create_table(
        "retrieval_hits",
        sa.Column("retrieval_run_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("citation_id", sa.Uuid(), nullable=False),
        sa.Column("final_rank", sa.Integer(), nullable=False),
        sa.Column("lexical_rank", sa.Integer(), nullable=True),
        sa.Column("vector_rank", sa.Integer(), nullable=True),
        sa.Column("fusion_score", sa.Numeric(precision=38, scale=12), nullable=False),
        sa.Column("rerank_reason", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("final_rank BETWEEN 1 AND 20", name="ck_retrieval_hits_rank"),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_retrieval_hits_chunk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["citation_id", "chunk_id"],
            ["citation_anchors.id", "citation_anchors.chunk_id"],
            name="fk_retrieval_hits_citation_chunk",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_run_id"],
            ["retrieval_runs.id"],
            name="fk_retrieval_hits_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_retrieval_hits"),
        sa.UniqueConstraint("retrieval_run_id", "chunk_id", name="uq_retrieval_hits_chunk"),
        sa.UniqueConstraint("retrieval_run_id", "final_rank", name="uq_retrieval_hits_rank"),
    )
    op.create_index(
        "ix_retrieval_hits_run_rank",
        "retrieval_hits",
        ["retrieval_run_id", "final_rank"],
        unique=False,
    )
    _create_immutability_guards()
    # ### end Alembic commands ###


def downgrade() -> None:
    _drop_immutability_guards()
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("ix_retrieval_hits_run_rank", table_name="retrieval_hits")
    op.drop_table("retrieval_hits")
    op.drop_index("ix_lexical_postings_index_token", table_name="lexical_postings")
    op.drop_table("lexical_postings")
    op.drop_table("embedding_records")
    op.drop_table("citation_anchors")
    op.drop_table("document_sections")
    op.drop_table("document_pages")
    op.drop_index("ix_document_chunks_parse_run_index", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_table("snapshot_document_versions")
    op.drop_index("ix_document_parse_runs_version_status", table_name="document_parse_runs")
    op.drop_table("document_parse_runs")
    op.drop_index("ix_document_versions_security_published", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("ix_retrieval_runs_security_scope", table_name="retrieval_runs")
    op.drop_table("retrieval_runs")
    op.drop_index("ix_lexical_index_versions_security_scope", table_name="lexical_index_versions")
    op.drop_table("lexical_index_versions")
    op.drop_table("vector_index_versions")
    op.drop_index("ix_logical_documents_security_type", table_name="logical_documents")
    op.drop_table("logical_documents")
    # ### end Alembic commands ###
