from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stock_research_agent.db.models.knowledge import DocumentChunk
from stock_research_agent.db.repositories.data_access import SqlAlchemyDataAccessRepository
from stock_research_agent.db.repositories.knowledge import SqlAlchemyKnowledgeRepository
from stock_research_agent.domain.data_access.schemas import (
    DataProviderWrite,
    IngestionRunWrite,
    ProviderRequestLogWrite,
    RawPayloadWrite,
    SourceDocumentWrite,
)
from stock_research_agent.domain.documents.chunking import DocumentChunker
from stock_research_agent.domain.documents.enums import (
    ContentKind,
    DocumentLanguage,
    LocatorType,
    ParseStatus,
    SourceVersionStatus,
    TrustLevel,
)
from stock_research_agent.domain.documents.schemas import (
    ChunkConfig,
    DocumentParseRunWrite,
    DocumentVersionWrite,
    ParseCompletion,
    ParsedDocument,
    ParsedSection,
)
from stock_research_agent.domain.retrieval.enums import IndexStatus
from stock_research_agent.domain.retrieval.schemas import (
    LexicalBuildRequest,
    LexicalIndexResult,
    LexicalPostingDraft,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
AS_OF = datetime(2026, 7, 10, 12, tzinfo=UTC)


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").lower() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments) or "integration" in arguments


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for Stage 6 repository tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture
def repository_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    command.downgrade(config, "0004_financial_normalization")
    command.upgrade(config, "head")
    engine = create_engine(TEST_DATABASE_URL)
    try:
        yield engine
    finally:
        engine.dispose()


def _seed_document_lineage(engine: Engine) -> tuple[UUID, DocumentVersionWrite]:
    token = uuid4().hex
    synthetic_security_id = uuid4()
    synthetic_issuer_id = uuid4()
    checksum = hashlib.sha256(f"synthetic-document-{token}".encode()).hexdigest()
    storage_uri = f"blob://synthetic/{token}"
    with Session(engine) as session:
        market_id = session.scalar(text("SELECT id FROM markets WHERE code = 'US_EQUITY'"))
        if market_id is None:
            market_id = uuid4()
            session.execute(
                text(
                    """
                    INSERT INTO markets (
                        id, code, name, country_code, default_currency_code, status
                    ) VALUES (
                        :market_id, 'US_EQUITY', 'US Equity', 'US', 'USD', 'UNKNOWN'
                    )
                    """
                ),
                {"market_id": market_id},
            )
        exchange_id = session.scalar(text("SELECT id FROM exchanges WHERE mic = 'XNAS'"))
        if exchange_id is None:
            exchange_id = uuid4()
            session.execute(
                text(
                    """
                    INSERT INTO exchanges (
                        id, market_id, mic, name, short_name, country_code,
                        timezone, default_currency_code, status
                    ) VALUES (
                        :exchange_id, :market_id, 'XNAS', 'Nasdaq', 'NASDAQ',
                        'US', 'America/New_York', 'USD', 'UNKNOWN'
                    )
                    """
                ),
                {"exchange_id": exchange_id, "market_id": market_id},
            )
        session.execute(
            text(
                """
                INSERT INTO issuers (
                    id, legal_name, normalized_legal_name, display_name,
                    normalized_display_name, country_code, issuer_status
                ) VALUES (
                    :issuer_id, :legal_name, :normalized_name, :display_name,
                    :normalized_display_name, 'US', 'ACTIVE'
                )
                """
            ),
            {
                "issuer_id": synthetic_issuer_id,
                "legal_name": f"Synthetic Test Issuer {token}",
                "normalized_name": f"SYNTHETIC TEST ISSUER {token.upper()}",
                "display_name": f"Synthetic Test {token[:8]}",
                "normalized_display_name": f"SYNTHETIC TEST {token[:8].upper()}",
            },
        )
        session.execute(
            text(
                """
                INSERT INTO securities (
                    id, issuer_id, exchange_id, symbol, normalized_symbol, display_name,
                    security_type, currency_code, listing_status, is_primary_listing
                ) VALUES (
                    :security_id, :issuer_id, :exchange_id, :symbol, :symbol,
                    :display_name, 'COMMON_STOCK', 'USD', 'ACTIVE', false
                )
                """
            ),
            {
                "security_id": synthetic_security_id,
                "issuer_id": synthetic_issuer_id,
                "exchange_id": exchange_id,
                "symbol": f"T{token[:15].upper()}",
                "display_name": f"Synthetic Test Security {token[:8]}",
            },
        )
        data_repository = SqlAlchemyDataAccessRepository(session)
        provider = data_repository.add_provider(
            DataProviderWrite(
                code=f"RAG_{token[:12].upper()}",
                name="Stage 6 synthetic repository test",
                provider_type="FIXTURE",
                status="APPROVED",
                terms_status="VERIFIED",
                capabilities=("DOCUMENT_DOWNLOAD",),
            )
        )
        ingestion = data_repository.create_ingestion_run(
            IngestionRunWrite(
                provider_id=provider.id,
                security_id=synthetic_security_id,
                category="SOURCE_DOCUMENTS",
                research_as_of_time=AS_OF,
                idempotency_key=f"rag:{token}",
                requested_at=AS_OF,
            )
        )
        request_log = data_repository.add_request_log(
            ProviderRequestLogWrite(
                ingestion_run_id=ingestion.id,
                provider_id=provider.id,
                caller_request_id=uuid4(),
                provider_request_id=f"rag-{token}",
                endpoint_name="synthetic.document",
                method="GET",
                safe_url="https://fixture.invalid/stage6/document",
                request_started_at=AS_OF,
                response_received_at=AS_OF,
                http_status=200,
                attempt=1,
                cache_status="NOT_APPLICABLE",
                response_size=32,
            )
        )
        payload = data_repository.add_raw_payload(
            RawPayloadWrite(
                ingestion_run_id=ingestion.id,
                provider_request_log_id=request_log.id,
                provider_id=provider.id,
                security_id=synthetic_security_id,
                category="SOURCE_DOCUMENTS",
                content_type="application/json",
                inline_json={"synthetic_test_only": True},
                checksum=checksum,
                source_published_at=AS_OF,
                retrieved_at=AS_OF,
                provider_version="fixture-v1",
                parser_version="fixture-v1",
                schema_version="fixture-v1",
                byte_size=32,
            )
        )
        source = data_repository.add_source_document(
            SourceDocumentWrite(
                security_id=synthetic_security_id,
                provider_id=provider.id,
                source_payload_id=payload.id,
                provider_document_id=f"synthetic-{token}",
                document_type="OTHER",
                title="Synthetic repository concurrency fixture",
                published_at=AS_OF,
                source_url="https://fixture.invalid/stage6/document",
                mime_type="text/plain",
                storage_uri=storage_uri,
                checksum=checksum,
                byte_size=32,
                document_status="AVAILABLE",
                retrieved_at=AS_OF,
            )
        )
        knowledge_repository = SqlAlchemyKnowledgeRepository(session)
        logical_document_id = knowledge_repository.get_or_create_logical_document(source.id)
        assert logical_document_id is not None
        value = DocumentVersionWrite(
            logical_document_id=logical_document_id,
            source_document_id=source.id,
            security_id=synthetic_security_id,
            provider_id=provider.id,
            source_payload_id=payload.id,
            version_number=1,
            supersedes_document_version_id=None,
            storage_uri=storage_uri,
            mime_type="text/plain",
            checksum=checksum,
            byte_size=32,
            published_at=AS_OF,
            filed_at=None,
            period_end=None,
            retrieved_at=AS_OF,
            document_language=DocumentLanguage.EN_US,
            trust_level=TrustLevel.TEST_FIXTURE,
            evidence_origin="SYNTHETIC_TEST_ONLY",
            access_mode="OFFLINE",
            live_status="NOT_LIVE",
            source_version_status=SourceVersionStatus.ACTIVE,
        )
        session.commit()
    return logical_document_id, value


def _create_version(engine: Engine, value: DocumentVersionWrite) -> UUID:
    with Session(engine) as session:
        record = SqlAlchemyKnowledgeRepository(session).add_version(value)
        session.commit()
        return record.id


def test_concurrent_document_version_creation_converges_on_one_record(
    repository_engine: Engine,
) -> None:
    logical_document_id, value = _seed_document_lineage(repository_engine)

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = tuple(
            executor.map(lambda _number: _create_version(repository_engine, value), range(2))
        )

    assert ids[0] == ids[1]
    with repository_engine.connect() as connection:
        count = connection.scalar(
            text(
                "SELECT count(*) FROM document_versions "
                "WHERE logical_document_id = :logical_document_id AND checksum = :checksum"
            ),
            {"logical_document_id": logical_document_id, "checksum": value.checksum},
        )
    assert count == 1


def test_concurrent_parse_run_creation_converges_on_one_record(
    repository_engine: Engine,
) -> None:
    _logical_document_id, version_value = _seed_document_lineage(repository_engine)
    version_id = _create_version(repository_engine, version_value)
    value = DocumentParseRunWrite(
        document_version_id=version_id,
        parser_name="plain-text",
        parser_version="parser-v1",
        sanitizer_version="sanitizer-v1",
        config_checksum="e" * 64,
    )

    def create() -> UUID:
        with Session(repository_engine) as session:
            record = SqlAlchemyKnowledgeRepository(session).create_parse_run(value)
            session.commit()
            return record.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = tuple(executor.map(lambda _number: create(), range(2)))

    assert ids[0] == ids[1]
    with repository_engine.connect() as connection:
        count = connection.scalar(
            text(
                "SELECT count(*) FROM document_parse_runs "
                "WHERE document_version_id = :version_id AND config_checksum = :checksum"
            ),
            {"version_id": version_id, "checksum": value.config_checksum},
        )
    assert count == 1


def test_concurrent_lexical_index_creation_converges_with_one_posting(
    repository_engine: Engine,
) -> None:
    _logical_document_id, version_value = _seed_document_lineage(repository_engine)
    version_id = _create_version(repository_engine, version_value)
    parse_value = DocumentParseRunWrite(
        document_version_id=version_id,
        parser_name="plain-text",
        parser_version="parser-v1",
        sanitizer_version="sanitizer-v1",
        config_checksum="f" * 64,
    )
    with Session(repository_engine) as session:
        repository = SqlAlchemyKnowledgeRepository(session)
        parse_run = repository.create_parse_run(parse_value)
        repository.finish_parse_run(
            parse_run.id,
            ParseCompletion(
                status=ParseStatus.PASS,
                canonical_text_checksum="1" * 64,
            ),
        )
        chunk = DocumentChunk(
            parse_run_id=parse_run.id,
            document_version_id=version_id,
            chunk_version="chunk-v1",
            chunk_index=0,
            text="synthetic lexical concurrency evidence",
            normalized_text="synthetic lexical concurrency evidence",
            language=DocumentLanguage.EN_US.value,
            content_kind="TEXT",
            locator_type="TEXT_OFFSET_RANGE",
            start_page=None,
            end_page=None,
            start_offset=0,
            end_offset=38,
            token_count=4,
            checksum="2" * 64,
            warnings=[],
        )
        session.add(chunk)
        session.commit()
        chunk_id = chunk.id

    index_version_id = uuid4()
    request = LexicalBuildRequest(
        index_name="stage6-synthetic",
        security_id=version_value.security_id,
        index_as_of_time=AS_OF,
    )
    result = LexicalIndexResult(
        status=IndexStatus.COMPLETE,
        index_version_id=index_version_id,
        document_set_checksum="3" * 64,
        document_count=1,
        chunk_count=1,
        average_chunk_length=Decimal("4"),
        postings=(
            LexicalPostingDraft(
                token="synthetic",
                chunk_id=chunk_id,
                term_frequency=1,
                field_kind="BODY",
                positions=(0,),
            ),
        ),
    )

    def persist() -> UUID:
        with Session(repository_engine) as session:
            stored = SqlAlchemyKnowledgeRepository(session).persist_lexical_index(request, result)
            session.commit()
            assert stored.index_version_id is not None
            return stored.index_version_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = tuple(executor.map(lambda _number: persist(), range(2)))

    assert ids == (index_version_id, index_version_id)
    with repository_engine.connect() as connection:
        index_count = connection.scalar(
            text("SELECT count(*) FROM lexical_index_versions WHERE id = :id"),
            {"id": index_version_id},
        )
        posting_count = connection.scalar(
            text("SELECT count(*) FROM lexical_postings WHERE index_version_id = :id"),
            {"id": index_version_id},
        )
    assert index_count == 1
    assert posting_count == 1


def test_json_chunk_persistence_retains_section_and_pointer_citation(
    repository_engine: Engine,
) -> None:
    _logical_document_id, version_value = _seed_document_lineage(repository_engine)
    version_id = _create_version(repository_engine, version_value)
    canonical = "synthetic JSON evidence"
    checksum = hashlib.sha256(canonical.encode()).hexdigest()
    pointer = "/facts/risk"
    parsed = ParsedDocument(
        canonical_text=canonical,
        canonical_text_checksum=checksum,
        sections=(
            ParsedSection(
                section_path=pointer,
                level=1,
                title=pointer,
                locator_type=LocatorType.JSON_POINTER,
                start_offset=0,
                end_offset=len(canonical),
                text_checksum=checksum,
                content_kind=ContentKind.JSON,
            ),
        ),
        status=ParseStatus.PASS,
    )
    with Session(repository_engine) as session:
        repository = SqlAlchemyKnowledgeRepository(session)
        run = repository.create_parse_run(
            DocumentParseRunWrite(
                document_version_id=version_id,
                parser_name="approved-json",
                parser_version="json-parser-v1",
                sanitizer_version="sanitizer-v1",
                config_checksum="7" * 64,
            )
        )
        repository.replace_running_artifacts(run.id, parsed)
        repository.finish_parse_run(
            run.id,
            ParseCompletion(status=ParseStatus.PASS, canonical_text_checksum=checksum),
        )
        chunks = DocumentChunker().chunk(parsed, ChunkConfig())
        chunk_ids = repository.add_chunks_and_citations(
            parse_run_id=run.id,
            document_version_id=version_id,
            chunks=chunks,
        )
        session.commit()
        row = session.execute(
            text(
                "SELECT citation.section_id, citation.locator, chunk.locator_type "
                "FROM citation_anchors citation "
                "JOIN document_chunks chunk ON chunk.id = citation.chunk_id "
                "WHERE chunk.id = :chunk_id"
            ),
            {"chunk_id": chunk_ids[0]},
        ).one()

    assert row.section_id is not None
    assert row.locator["json_pointer"] == pointer
    assert row.locator_type == LocatorType.JSON_POINTER.value


def test_database_rejects_cross_document_supersession_and_preserves_old_versions(
    repository_engine: Engine,
) -> None:
    first_logical, first_value = _seed_document_lineage(repository_engine)
    _second_logical, second_value = _seed_document_lineage(repository_engine)
    first_id = _create_version(repository_engine, first_value)
    second_id = _create_version(repository_engine, second_value)

    with Session(repository_engine) as session, pytest.raises(IntegrityError):
        session.execute(
            text(
                """
                INSERT INTO document_versions (
                    id, logical_document_id, source_document_id, security_id, provider_id,
                    source_payload_id, version_number, supersedes_document_version_id,
                    storage_uri, mime_type, checksum_algorithm, checksum, byte_size,
                    published_at, filed_at, period_end, retrieved_at, document_language,
                    trust_level, evidence_origin, access_mode, live_status, source_version_status
                )
                SELECT :new_id, :first_logical, source_document_id, security_id, provider_id,
                    source_payload_id, 2, NULL, storage_uri, mime_type, checksum_algorithm,
                    :checksum, byte_size, published_at, filed_at, period_end, retrieved_at,
                    document_language, trust_level, evidence_origin, access_mode, live_status,
                    source_version_status
                FROM document_versions WHERE id = :second_id
                """
            ),
            {
                "new_id": uuid4(),
                "first_logical": first_logical,
                "second_id": second_id,
                "checksum": "8" * 64,
            },
        )
        session.commit()

    with Session(repository_engine) as session, pytest.raises(IntegrityError):
        session.execute(
            text(
                """
                INSERT INTO document_versions (
                    id, logical_document_id, source_document_id, security_id, provider_id,
                    source_payload_id, version_number, supersedes_document_version_id,
                    storage_uri, mime_type, checksum_algorithm, checksum, byte_size,
                    published_at, filed_at, period_end, retrieved_at, document_language,
                    trust_level, evidence_origin, access_mode, live_status, source_version_status
                )
                SELECT :new_id, logical_document_id, source_document_id, security_id, provider_id,
                    source_payload_id, 2, :first_id, storage_uri, mime_type, checksum_algorithm,
                    :checksum, byte_size, published_at, filed_at, period_end, retrieved_at,
                    document_language, trust_level, evidence_origin, access_mode, live_status,
                    source_version_status
                FROM document_versions WHERE id = :second_id
                """
            ),
            {
                "new_id": uuid4(),
                "first_id": first_id,
                "second_id": second_id,
                "checksum": "9" * 64,
            },
        )
        session.commit()

    for statement in (
        "UPDATE document_versions SET source_version_status = 'WITHDRAWN' WHERE id = :id",
        "DELETE FROM document_versions WHERE id = :id",
    ):
        with Session(repository_engine) as session, pytest.raises(IntegrityError):
            session.execute(text(statement), {"id": first_id})
            session.commit()

    with repository_engine.connect() as connection:
        surviving_ids = set(
            connection.execute(
                text("SELECT id FROM document_versions WHERE id IN (:first_id, :second_id)"),
                {"first_id": first_id, "second_id": second_id},
            ).scalars()
        )
    assert surviving_ids == {first_id, second_id}
