from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stock_research_agent.db.repositories.knowledge import SqlAlchemyKnowledgeRepository
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.domain.retrieval.enums import RetrievalMode, RetrievalStatus
from stock_research_agent.domain.retrieval.schemas import RetrievalCompletion, RetrievalRunWrite
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_SECURITY_ID,
    SecurityMasterSeedService,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
STAGE6_TABLES = {
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


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").lower() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments) or "integration" in arguments


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 6 migration tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture
def migration_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL)
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    command.downgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "0004_financial_normalization")
    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    try:
        yield engine
    finally:
        command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
        engine.dispose()


def test_stage6_upgrade_downgrade_upgrade_preserves_stage5(migration_engine: Engine) -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    assert STAGE6_TABLES <= set(inspect(migration_engine).get_table_names())

    command.downgrade(config, "0004_financial_normalization")
    after = set(inspect(migration_engine).get_table_names())
    assert not (STAGE6_TABLES & after)
    assert "derived_metrics" in after

    command.upgrade(config, "head")
    assert STAGE6_TABLES <= set(inspect(migration_engine).get_table_names())


def test_stage6_catalog_has_immutability_and_section_cycle_triggers(
    migration_engine: Engine,
) -> None:
    with migration_engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE NOT tgisinternal AND tgrelid IN "
                    "(SELECT oid FROM pg_class WHERE relname = ANY(:tables))"
                ),
                {"tables": list(STAGE6_TABLES)},
            )
            .scalars()
            .all()
        )
    assert "trg_document_versions_immutable" in rows
    assert "trg_document_chunks_immutable" in rows
    assert "trg_retrieval_hits_immutable" in rows
    assert "trg_retrieval_runs_completed_immutable" in rows
    assert "trg_document_sections_no_cycles" in rows
    assert "trg_document_versions_validate_lineage" in rows
    assert "trg_document_versions_validate_supersession" in rows
    assert "trg_citation_anchors_validate_lineage" in rows


def test_stage6_catalog_requires_citations_and_native_locator_foreign_keys(
    migration_engine: Engine,
) -> None:
    inspector = inspect(migration_engine)
    hit_columns = {column["name"]: column for column in inspector.get_columns("retrieval_hits")}
    assert hit_columns["citation_id"]["nullable"] is False
    hit_foreign_keys = {
        constraint["name"]: tuple(constraint["constrained_columns"])
        for constraint in inspector.get_foreign_keys("retrieval_hits")
    }
    assert hit_foreign_keys["fk_retrieval_hits_citation_chunk"] == (
        "citation_id",
        "chunk_id",
    )
    citation_foreign_keys = {
        constraint["name"] for constraint in inspector.get_foreign_keys("citation_anchors")
    }
    assert "fk_citation_anchors_page" in citation_foreign_keys
    assert "fk_citation_anchors_section" in citation_foreign_keys


def test_stage6_catalog_matches_models_and_has_no_business_rows(migration_engine: Engine) -> None:
    inspector = inspect(migration_engine)
    for table_name in STAGE6_TABLES:
        assert inspector.get_pk_constraint(table_name)["name"] == f"pk_{table_name}"
        with migration_engine.connect() as connection:
            assert connection.scalar(text(f'SELECT count(*) FROM "{table_name}"')) == 0


def test_retrieval_run_repository_reuses_unique_fingerprint_and_terminal_is_immutable(
    migration_engine: Engine,
) -> None:
    with Session(migration_engine) as session:
        SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
        session.commit()
        repository = SqlAlchemyKnowledgeRepository(session)
        value = RetrievalRunWrite(
            request_fingerprint="a" * 64,
            request_basis_fingerprint="c" * 64,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            snapshot_id=None,
            research_as_of_time=datetime(2026, 7, 10, 12, tzinfo=UTC),
            mode=RetrievalMode.LEXICAL,
            original_query="risk",
            normalized_query="risk",
            max_results=10,
            tokenizer_version="tokenizer-v1",
            lexical_index_version_id=None,
            vector_index_version_id=None,
            fusion_version="fusion-v1",
            reranker_version="stable-reranker-v1",
            status=RetrievalStatus.BLOCKED,
        )

        first = repository.create_run(value)
        session.commit()
        second = repository.create_run(value)
        assert second.id == first.id
        terminal = repository.finish_run(
            first.id,
            RetrievalCompletion(status=RetrievalStatus.BLOCKED, warnings=("NO_INDEX",)),
        )
        session.commit()
        assert terminal.completed_at is not None

        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE retrieval_runs SET normalized_query = 'changed' WHERE id = :id"),
                {"id": first.id},
            )
            session.commit()
        session.rollback()


def test_concurrent_retrieval_run_creation_converges_on_one_record(
    migration_engine: Engine,
) -> None:
    with Session(migration_engine) as session:
        SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
        session.commit()
    value = RetrievalRunWrite(
        request_fingerprint="b" * 64,
        request_basis_fingerprint="d" * 64,
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        snapshot_id=None,
        research_as_of_time=datetime(2026, 7, 10, 12, tzinfo=UTC),
        mode=RetrievalMode.LEXICAL,
        original_query="revenue",
        normalized_query="revenue",
        max_results=10,
        tokenizer_version="tokenizer-v1",
        lexical_index_version_id=None,
        vector_index_version_id=None,
        fusion_version="fusion-v1",
        reranker_version="stable-reranker-v1",
        status=RetrievalStatus.BLOCKED,
    )

    def create() -> UUID:
        with Session(migration_engine) as session:
            row = SqlAlchemyKnowledgeRepository(session).create_run(value)
            session.commit()
            return row.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = tuple(executor.map(lambda _number: create(), range(2)))

    assert ids[0] == ids[1]
    with migration_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM retrieval_runs WHERE request_fingerprint = :fingerprint"
                ),
                {"fingerprint": value.request_fingerprint},
            )
            == 1
        )
