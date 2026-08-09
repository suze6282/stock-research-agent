from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Engine, Numeric, cast, create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.models import DataProvider
from stock_research_agent.db.repositories.data_access import SqlAlchemyDataAccessRepository
from stock_research_agent.domain.data_access.enums import DataCategory
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.data_access.repositories import StoredDataValidationError
from stock_research_agent.domain.data_access.schemas import (
    CorporateActionWrite,
    DailyPriceBarWrite,
    DataProviderWrite,
    DataSnapshotUpdate,
    DataSnapshotWrite,
    IngestionRunUpdate,
    IngestionRunWrite,
    ProviderFinancialFactWrite,
    ProviderInstrumentMappingWrite,
    ProviderRequestLogWrite,
    RawPayloadWrite,
    SnapshotEvidenceAggregateRecord,
    SnapshotItemWrite,
    SourceDocumentWrite,
)
from stock_research_agent.tools.registry import create_tool_registry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_explicitly_selected() -> bool:
    arguments = [argument.replace("\\", "/").lower() for argument in sys.argv[1:]]
    return any("tests/integration" in argument for argument in arguments)


if TEST_DATABASE_URL is None and _integration_was_explicitly_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for PostgreSQL integration tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture
def repository_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=TEST_DATABASE_URL,
    )
    assert settings.database_url is not None
    engine = create_engine(settings.database_url)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    previous = os.environ.get("DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO markets
                    (id, code, name, country_code, default_currency_code, status)
                VALUES
                    ('10000000-0000-0000-0000-000000000001', 'US_EQUITY',
                     'US Equity', 'US', 'USD', 'ACTIVE');
                INSERT INTO exchanges
                    (id, market_id, mic, name, short_name, country_code, timezone,
                     default_currency_code, status)
                VALUES
                    ('20000000-0000-0000-0000-000000000001',
                     '10000000-0000-0000-0000-000000000001', 'XNAS', 'Nasdaq',
                     'Nasdaq', 'US', 'America/New_York', 'USD', 'ACTIVE');
                INSERT INTO issuers
                    (id, legal_name, normalized_legal_name, display_name,
                     normalized_display_name, country_code, issuer_status)
                VALUES
                    ('30000000-0000-0000-0000-000000000001', 'Example Inc.',
                     'EXAMPLE INC', 'Example', 'EXAMPLE', 'US', 'ACTIVE');
                INSERT INTO securities
                    (id, issuer_id, exchange_id, symbol, normalized_symbol,
                     display_name, security_type, currency_code, listing_status,
                     is_primary_listing)
                VALUES
                    ('40000000-0000-0000-0000-000000000001',
                     '30000000-0000-0000-0000-000000000001',
                     '20000000-0000-0000-0000-000000000001', 'EXM', 'EXM',
                     'Example', 'COMMON_STOCK', 'USD', 'DELISTED', true)
                """
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()
        if previous is None:
            monkeypatch.delenv("DATABASE_URL", raising=False)
        else:
            monkeypatch.setenv("DATABASE_URL", previous)


SECURITY_ID = UUID("40000000-0000-0000-0000-000000000001")
AS_OF = datetime(2026, 7, 10, 20, tzinfo=UTC)


def _write_complete_lineage(repository: SqlAlchemyDataAccessRepository) -> dict[str, UUID]:
    provider = repository.add_provider(
        DataProviderWrite(
            code="FIXTURE_STAGE1",
            name="Stage 1 fixture",
            provider_type="FIXTURE",
            status="APPROVED",
            terms_status="VERIFIED",
            capabilities=("DAILY_PRICES", "FINANCIAL_FACTS"),
        )
    )
    mapping = repository.add_provider_mapping(
        ProviderInstrumentMappingWrite(
            provider_id=provider.id,
            security_id=SECURITY_ID,
            provider_symbol="EXM",
            provider_exchange_code="XNAS",
            valid_from=date(2020, 1, 1),
            is_primary=True,
            metadata={"origin": "fixture"},
            source_name="stage-1 evidence",
        )
    )
    run = repository.create_ingestion_run(
        IngestionRunWrite(
            provider_id=provider.id,
            security_id=SECURITY_ID,
            category="DAILY_PRICES",
            research_as_of_time=AS_OF,
            idempotency_key="fixture:exm:20260710",
            requested_at=AS_OF,
        )
    )
    request = repository.add_request_log(
        ProviderRequestLogWrite(
            ingestion_run_id=run.id,
            provider_id=provider.id,
            caller_request_id=UUID("71000000-0000-0000-0000-000000000001"),
            provider_request_id="fixture-request:one",
            endpoint_name="fixture.daily",
            method="GET",
            safe_url="https://fixture.invalid/stage1/exm",
            request_started_at=AS_OF,
            response_received_at=AS_OF,
            http_status=200,
            attempt=1,
            cache_status="NOT_APPLICABLE",
            response_size=128,
        )
    )
    payload = repository.add_raw_payload(
        RawPayloadWrite(
            ingestion_run_id=run.id,
            provider_request_log_id=request.id,
            provider_id=provider.id,
            security_id=SECURITY_ID,
            category="DAILY_PRICES",
            content_type="application/json",
            inline_json={"fixture": True},
            checksum="a" * 64,
            source_published_at=None,
            retrieved_at=AS_OF,
            provider_version="1.0.0",
            parser_version="1.0.0",
            schema_version="1.0.0",
            byte_size=128,
        )
    )
    return {
        "provider": provider.id,
        "mapping": mapping.id,
        "run": run.id,
        "request": request.id,
        "payload": payload.id,
    }


def test_explicit_writes_preserve_exact_values_and_caller_owns_commit(
    repository_engine: Engine,
) -> None:
    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        bar = repository.add_daily_price_bar(
            DailyPriceBarWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_symbol="EXM",
                trading_date=date(2026, 7, 10),
                close=Decimal("979.300000000001"),
                volume=31768090,
                currency_code="USD",
                adjustment_type="UNADJUSTED",
                source_published_at=None,
                retrieved_at=AS_OF,
            )
        )
        action = repository.add_corporate_action(
            CorporateActionWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_action_id="action-1",
                action_type="OTHER",
                status="UNKNOWN",
                source_published_at=None,
                retrieved_at=AS_OF,
            )
        )
        document = repository.add_source_document(
            SourceDocumentWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_document_id="doc-1",
                document_type="OTHER",
                title="Metadata only",
                source_url="https://www.sec.gov/example",
                document_status="METADATA_ONLY",
                retrieved_at=AS_OF,
            )
        )
        fact = repository.add_financial_fact(
            ProviderFinancialFactWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                document_id=document.id,
                statement_type="OTHER",
                provider_concept="us-gaap:Example",
                reported_label="Reported Example",
                taxonomy="us-gaap",
                context_id="ctx-1",
                dimensions={},
                value=Decimal("1234567890.123456789012"),
                unit="USD",
                currency_code="USD",
                source_published_at=None,
                retrieved_at=AS_OF,
            )
        )
        snapshot = repository.add_snapshot(
            DataSnapshotWrite(
                security_id=SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=1,
                status="BUILDING",
                formula_version="raw-data-v1",
            )
        )
        item = repository.add_snapshot_item(
            SnapshotItemWrite(
                snapshot_id=snapshot.id,
                provider_id=ids["provider"],
                category="DAILY_PRICES",
                source_record_type="daily_price_bars",
                source_record_id=bar.id,
                source_published_at=None,
                retrieved_at=AS_OF,
                checksum_input="daily_price_bars:" + str(bar.id),
                checksum="c" * 64,
            )
        )
        snapshot = repository.update_snapshot(
            snapshot.id,
            DataSnapshotUpdate(
                status="PARTIAL",
                completed_at=AS_OF,
                checksum="b" * 64,
                notes="Unknown publication time retained",
            ),
        )
        repository.update_ingestion_run(
            ids["run"],
            IngestionRunUpdate(
                status="PARTIAL",
                started_at=AS_OF,
                completed_at=AS_OF,
                request_count=1,
                records_received=4,
                records_stored=4,
                warning_count=1,
            ),
        )
        assert bar.close == Decimal("979.300000000001")
        assert fact.value == Decimal("1234567890.123456789012")
        assert action.id and document.id and item.id
        session.commit()

    with Session(repository_engine) as verification:
        assert verification.scalar(select(func.count()).select_from(DataProvider)) == 1


def test_rollback_integrity_propagation_and_revision_coexistence(repository_engine: Engine) -> None:
    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        _write_complete_lineage(repository)
        session.rollback()
    with Session(repository_engine) as verification:
        assert verification.scalar(select(func.count()).select_from(DataProvider)) == 0

    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        common = dict(
            security_id=SECURITY_ID,
            provider_id=ids["provider"],
            provider_symbol="EXM",
            trading_date=date(2026, 7, 10),
            close=Decimal("10.00"),
            currency_code="USD",
            adjustment_type="UNADJUSTED",
            retrieved_at=AS_OF,
        )
        repository.add_daily_price_bar(
            DailyPriceBarWrite(source_payload_id=ids["payload"], **common)
        )
        with pytest.raises(IntegrityError):
            repository.add_daily_price_bar(
                DailyPriceBarWrite(source_payload_id=ids["payload"], **common)
            )
        session.rollback()


def test_bounded_as_of_reads_are_stable_do_not_autoflush_and_hide_payload_body(
    repository_engine: Engine,
) -> None:
    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        for suffix, trading_date, published_at, close in (
            ("1", date(2026, 7, 9), None, "9.00"),
            ("2", date(2026, 7, 10), AS_OF, "10.00"),
            ("3", date(2026, 7, 11), AS_OF, "11.00"),
            ("4", date(2026, 7, 8), datetime(2026, 7, 11, tzinfo=UTC), "12.00"),
        ):
            payload = repository.add_raw_payload(
                RawPayloadWrite(
                    ingestion_run_id=ids["run"],
                    provider_request_log_id=ids["request"],
                    provider_id=ids["provider"],
                    security_id=SECURITY_ID,
                    category="DAILY_PRICES",
                    content_type="application/json",
                    storage_uri=f"blob://fixture/payload-{suffix}",
                    checksum=suffix * 64,
                    source_published_at=published_at,
                    retrieved_at=AS_OF,
                    provider_version="1.0.0",
                    parser_version="1.0.0",
                    schema_version="1.0.0",
                    byte_size=1,
                )
            )
            repository.add_daily_price_bar(
                DailyPriceBarWrite(
                    security_id=SECURITY_ID,
                    provider_id=ids["provider"],
                    source_payload_id=payload.id,
                    provider_symbol="EXM",
                    trading_date=trading_date,
                    close=Decimal(close),
                    currency_code="USD",
                    adjustment_type="UNADJUSTED",
                    source_published_at=published_at,
                    retrieved_at=AS_OF,
                )
            )
        session.commit()

        session.add(
            DataProvider(
                code="invalid lowercase",
                name="pending invalid",
                provider_type="FIXTURE",
                status="APPROVED",
                terms_status="VERIFIED",
                capabilities=[],
            )
        )
        rows = repository.list_daily_history(
            SECURITY_ID,
            research_as_of_time=AS_OF,
            local_trading_date=date(2026, 7, 10),
            limit=2,
        )
        assert [row.close for row in rows] == [
            Decimal("10.000000000000"),
            Decimal("9.000000000000"),
        ]
        assert rows[1].source_published_at is None
        metadata = repository.list_raw_payload_lineage(ids["run"], limit=5)
        assert metadata
        assert all(not hasattr(row, "inline_json") for row in metadata)
        assert all(not hasattr(row, "storage_uri") for row in metadata)
        assert session.new
        with pytest.raises(ValueError):
            repository.list_daily_history(
                SECURITY_ID,
                research_as_of_time=AS_OF,
                local_trading_date=None,
                limit=101,
            )
        session.rollback()


def test_active_mapping_and_partial_snapshot_remain_visible(repository_engine: Engine) -> None:
    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        _write_complete_lineage(repository)
        snapshot = repository.add_snapshot(
            DataSnapshotWrite(
                security_id=SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=1,
                status="BUILDING",
                formula_version="raw-data-v1",
            )
        )
        snapshot = repository.update_snapshot(
            snapshot.id,
            DataSnapshotUpdate(
                status="PARTIAL",
                completed_at=AS_OF,
                checksum="d" * 64,
            ),
        )
        session.commit()
        mapping = repository.get_active_mapping(SECURITY_ID, "FIXTURE_STAGE1", date(2026, 7, 10))
        assert mapping is not None and mapping.provider_symbol == "EXM"
        latest = repository.get_latest_eligible_snapshot(SECURITY_ID, AS_OF)
        assert latest is not None and latest.id == snapshot.id and latest.status == "PARTIAL"


def test_catalog_run_lineage_and_all_category_reads_are_bounded_and_safe(
    repository_engine: Engine,
) -> None:
    future = datetime(2026, 7, 11, tzinfo=UTC)
    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        bar = repository.add_daily_price_bar(
            DailyPriceBarWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_symbol="EXM",
                trading_date=date(2026, 7, 10),
                close=Decimal("10.25"),
                currency_code="USD",
                adjustment_type="UNADJUSTED",
                source_published_at=None,
                retrieved_at=AS_OF,
            )
        )
        current_action = repository.add_corporate_action(
            CorporateActionWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_action_id="current-action",
                action_type="OTHER",
                status="UNKNOWN",
                source_published_at=None,
                retrieved_at=AS_OF,
            )
        )
        repository.add_corporate_action(
            CorporateActionWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_action_id="future-action",
                action_type="OTHER",
                status="ANNOUNCED",
                source_published_at=future,
                retrieved_at=AS_OF,
            )
        )
        current_document = repository.add_source_document(
            SourceDocumentWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_document_id="current-doc",
                document_type="OTHER",
                title="Current metadata",
                published_at=None,
                source_url="https://www.sec.gov/current",
                storage_uri="blob://fixture/current-doc",
                checksum="e" * 64,
                byte_size=10,
                document_status="AVAILABLE",
                retrieved_at=AS_OF,
            )
        )
        repository.add_source_document(
            SourceDocumentWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_document_id="future-doc",
                document_type="OTHER",
                title="Future metadata",
                published_at=future,
                source_url="https://www.sec.gov/future",
                document_status="METADATA_ONLY",
                retrieved_at=AS_OF,
            )
        )
        current_fact = repository.add_financial_fact(
            ProviderFinancialFactWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                document_id=current_document.id,
                statement_type="OTHER",
                provider_concept="raw:Current",
                reported_label="Current raw label",
                taxonomy="raw-taxonomy",
                context_id="raw-context",
                dimensions={"reported": "yes"},
                value=Decimal("1.000000000001"),
                source_published_at=None,
                retrieved_at=AS_OF,
            )
        )
        repository.add_financial_fact(
            ProviderFinancialFactWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                statement_type="OTHER",
                provider_concept="raw:Future",
                dimensions={},
                value=Decimal("2"),
                source_published_at=future,
                retrieved_at=AS_OF,
            )
        )
        snapshot = repository.add_snapshot(
            DataSnapshotWrite(
                security_id=SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=1,
                status="BUILDING",
                formula_version="raw-data-v1",
            )
        )
        for category, record_type, record_id, checksum_character in (
            ("FINANCIAL_FACTS", "provider_financial_facts", current_fact.id, "1"),
            ("DAILY_PRICES", "daily_price_bars", bar.id, "2"),
            ("CORPORATE_ACTIONS", "corporate_actions", current_action.id, "3"),
        ):
            repository.add_snapshot_item(
                SnapshotItemWrite(
                    snapshot_id=snapshot.id,
                    provider_id=ids["provider"],
                    category=category,
                    source_record_type=record_type,
                    source_record_id=record_id,
                    source_published_at=None,
                    retrieved_at=AS_OF,
                    checksum_input=f"{record_type}:{record_id}",
                    checksum=checksum_character * 64,
                )
            )
        snapshot = repository.update_snapshot(
            snapshot.id,
            DataSnapshotUpdate(
                status="PARTIAL",
                completed_at=AS_OF,
                checksum="f" * 64,
            ),
        )
        session.commit()

        assert repository.get_provider("FIXTURE_STAGE1") is not None
        assert [record.code for record in repository.list_providers(1)] == ["FIXTURE_STAGE1"]
        assert repository.get_ingestion_run(ids["run"]) is not None
        assert (
            repository.get_ingestion_run_by_idempotency_key("fixture:exm:20260710").id == ids["run"]
        )
        assert [record.id for record in repository.list_request_lineage(ids["run"], 1)] == [
            ids["request"]
        ]
        assert repository.get_latest_close(SECURITY_ID, AS_OF, date(2026, 7, 10)).id == bar.id
        actions = repository.list_corporate_actions(SECURITY_ID, AS_OF, 10)
        assert [record.id for record in actions] == [current_action.id]
        facts = repository.list_financial_facts(SECURITY_ID, AS_OF, 10)
        assert [record.id for record in facts] == [current_fact.id]
        assert facts[0].reported_label == "Current raw label"
        assert facts[0].taxonomy == "raw-taxonomy"
        assert facts[0].context_id == "raw-context"
        documents = repository.list_source_documents(SECURITY_ID, AS_OF, 10)
        assert [record.id for record in documents] == [current_document.id]
        assert not hasattr(documents[0], "storage_uri")
        items = repository.list_snapshot_items(snapshot.id, 2)
        assert len(items) == 2
        assert [(item.category, item.source_record_type) for item in items] == sorted(
            (item.category, item.source_record_type) for item in items
        )


def test_correction_payload_revisions_coexist_without_float_conversion(
    repository_engine: Engine,
) -> None:
    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        second_payload = repository.add_raw_payload(
            RawPayloadWrite(
                ingestion_run_id=ids["run"],
                provider_request_log_id=ids["request"],
                provider_id=ids["provider"],
                security_id=SECURITY_ID,
                category="DAILY_PRICES",
                content_type="application/json",
                inline_json={"revision": 2},
                checksum="9" * 64,
                source_published_at=AS_OF,
                retrieved_at=AS_OF,
                provider_version="1.0.0",
                parser_version="1.0.0",
                schema_version="1.0.0",
                byte_size=10,
            )
        )
        for payload_id, close in (
            (ids["payload"], Decimal("10.000000000001")),
            (second_payload.id, Decimal("10.000000000002")),
        ):
            repository.add_daily_price_bar(
                DailyPriceBarWrite(
                    security_id=SECURITY_ID,
                    provider_id=ids["provider"],
                    source_payload_id=payload_id,
                    provider_symbol="EXM",
                    trading_date=date(2026, 7, 10),
                    close=close,
                    currency_code="USD",
                    adjustment_type="UNADJUSTED",
                    source_published_at=AS_OF,
                    retrieved_at=AS_OF,
                )
            )
        session.commit()
        records = repository.list_daily_history(SECURITY_ID, AS_OF, date(2026, 7, 10), 10)
        assert {record.close for record in records} == {
            Decimal("10.000000000001"),
            Decimal("10.000000000002"),
        }
        assert all(isinstance(record.close, Decimal) for record in records)


def test_dto_rejects_values_postgres_would_round_before_any_repository_write(
    repository_engine: Engine,
) -> None:
    value_requiring_rounding = Decimal("1.1234567890123")
    with Session(repository_engine) as session:
        rounded = session.scalar(select(cast(value_requiring_rounding, Numeric(38, 12))))
        assert rounded == Decimal("1.123456789012")
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        with pytest.raises(ValidationError):
            repository.add_daily_price_bar(
                DailyPriceBarWrite(
                    security_id=SECURITY_ID,
                    provider_id=ids["provider"],
                    source_payload_id=ids["payload"],
                    provider_symbol="EXM",
                    trading_date=date(2026, 7, 10),
                    close=value_requiring_rounding,
                    currency_code="USD",
                    adjustment_type="UNADJUSTED",
                    retrieved_at=AS_OF,
                )
            )
        assert repository.list_daily_history(SECURITY_ID, AS_OF, None, 10) == ()

        negative_fact = repository.add_financial_fact(
            ProviderFinancialFactWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                statement_type="OTHER",
                provider_concept="raw:NetLoss",
                dimensions={},
                value=Decimal("-123.123456789012"),
                retrieved_at=AS_OF,
            )
        )
        assert negative_fact.value == Decimal("-123.123456789012")


def test_ingestion_run_update_is_a_true_patch_and_preserves_omitted_fields(
    repository_engine: Engine,
) -> None:
    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        running = repository.update_ingestion_run(
            ids["run"],
            IngestionRunUpdate(
                status="RUNNING",
                started_at=AS_OF,
                request_count=5,
                records_received=4,
                records_stored=3,
                warning_count=2,
                error_code="RETRYABLE",
                safe_error_message="temporary provider failure",
            ),
        )
        terminal = repository.update_ingestion_run(
            ids["run"],
            IngestionRunUpdate(
                status="PARTIAL",
                completed_at=AS_OF,
                warning_count=0,
            ),
        )
        assert terminal.started_at == running.started_at
        assert terminal.request_count == 5
        assert terminal.records_received == 4
        assert terminal.records_stored == 3
        assert terminal.warning_count == 0
        assert terminal.error_code == "RETRYABLE"
        assert terminal.safe_error_message == "temporary provider failure"

        counts_only = repository.update_ingestion_run(
            ids["run"], IngestionRunUpdate(records_stored=0, error_code=None)
        )
        assert counts_only.status == "PARTIAL"
        assert counts_only.records_stored == 0
        assert counts_only.error_code is None
        assert counts_only.safe_error_message == "temporary provider failure"


class SessionLifecycleSpy(Session):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1
        super().commit()

    def rollback(self) -> None:
        self.rollback_calls += 1
        super().rollback()

    def close(self) -> None:
        self.close_calls += 1
        super().close()


def test_repository_never_owns_session_lifecycle_and_collection_sql_has_limit(
    repository_engine: Engine,
) -> None:
    statements: list[str] = []

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(repository_engine, "before_cursor_execute", capture_statement)
    session = SessionLifecycleSpy(bind=repository_engine)
    try:
        repository = SqlAlchemyDataAccessRepository(session)
        _write_complete_lineage(repository)
        repository.list_providers(1)
        assert session.commit_calls == 0
        assert session.rollback_calls == 0
        assert session.close_calls == 0
        provider_select = next(
            statement for statement in reversed(statements) if "FROM data_providers" in statement
        )
        assert "LIMIT" in provider_select.upper()
    finally:
        session.close()
        event.remove(repository_engine, "before_cursor_execute", capture_statement)
    assert session.close_calls == 1


def test_safe_metadata_reads_project_out_raw_body_and_storage_uri_at_sql_level(
    repository_engine: Engine,
) -> None:
    statements: list[str] = []

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        repository.add_source_document(
            SourceDocumentWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_document_id="projected-doc",
                document_type="OTHER",
                title="Projected metadata",
                source_url="https://www.sec.gov/projected",
                storage_uri="blob://fixture/projected-doc",
                document_status="AVAILABLE",
                retrieved_at=AS_OF,
            )
        )
        session.commit()
        event.listen(repository_engine, "before_cursor_execute", capture_statement)
        try:
            repository.list_raw_payload_lineage(ids["run"], 10)
            raw_select = statements[-1]
            repository.list_source_documents(SECURITY_ID, AS_OF, 10)
            document_select = statements[-1]
        finally:
            event.remove(repository_engine, "before_cursor_execute", capture_statement)

    assert "inline_json" not in raw_select
    assert "storage_uri" not in raw_select
    assert "storage_uri" not in document_select
    assert "LIMIT" in raw_select.upper()
    assert "LIMIT" in document_select.upper()


def test_maximum_legal_numeric_38_12_boundaries_round_trip_exactly(
    repository_engine: Engine,
) -> None:
    maximum = Decimal("99999999999999999999999999.999999999999")
    negative_maximum = Decimal("-99999999999999999999999999.999999999999")
    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        bar = repository.add_daily_price_bar(
            DailyPriceBarWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_symbol="EXM",
                trading_date=date(2026, 7, 10),
                close=maximum,
                currency_code="USD",
                adjustment_type="UNADJUSTED",
                retrieved_at=AS_OF,
            )
        )
        fact = repository.add_financial_fact(
            ProviderFinancialFactWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                statement_type="OTHER",
                provider_concept="raw:MaximumNegative",
                dimensions={},
                value=negative_maximum,
                retrieved_at=AS_OF,
            )
        )
        session.commit()
        assert repository.get_latest_close(SECURITY_ID, AS_OF, None).id == bar.id
        assert repository.get_latest_close(SECURITY_ID, AS_OF, None).close == maximum
        facts = repository.list_financial_facts(SECURITY_ID, AS_OF, 10)
        stored = next(record for record in facts if record.id == fact.id)
        assert stored.value == negative_maximum


def test_legacy_unsafe_urls_never_escape_repository_read_boundaries(
    repository_engine: Engine,
) -> None:
    sentinel = "SECRET_SENTINEL"
    unsafe_url = f"https://legacy.example/data?api_key={sentinel}"
    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        document = repository.add_source_document(
            SourceDocumentWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_document_id="legacy-unsafe-doc",
                document_type="OTHER",
                title="Legacy unsafe metadata",
                source_url="https://legacy.example/safe",
                document_status="METADATA_ONLY",
                retrieved_at=AS_OF,
            )
        )
        session.commit()

    cases = (
        (
            "UPDATE data_providers SET base_url = :unsafe WHERE id = :id",
            ids["provider"],
            lambda repository: repository.get_provider("FIXTURE_STAGE1"),
        ),
        (
            "UPDATE provider_request_logs SET safe_url = :unsafe WHERE id = :id",
            ids["request"],
            lambda repository: repository.list_request_lineage(ids["run"], 10),
        ),
        (
            "UPDATE source_documents SET source_url = :unsafe WHERE id = :id",
            document.id,
            lambda repository: repository.list_source_documents(SECURITY_ID, AS_OF, 10),
        ),
    )
    for statement, record_id, query in cases:
        with Session(repository_engine) as session:
            session.execute(text(statement), {"unsafe": unsafe_url, "id": record_id})
            session.commit()
            repository = SqlAlchemyDataAccessRepository(session)
            with pytest.raises(StoredDataValidationError) as captured:
                query(repository)
            assert str(captured.value) == "Stored data failed safe validation"
            assert sentinel not in str(captured.value)
            assert sentinel not in repr(captured.value)
            assert captured.value.__cause__ is None
            assert not isinstance(captured.value, ValidationError)


def test_tool_read_ports_select_only_exact_ids_and_category_items(
    repository_engine: Engine,
) -> None:
    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        older_bar = repository.add_daily_price_bar(
            DailyPriceBarWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_symbol="EXM",
                trading_date=date(2026, 7, 9),
                close=Decimal("10.25"),
                currency_code="USD",
                adjustment_type="UNADJUSTED",
                retrieved_at=AS_OF,
            )
        )
        newer_bar = repository.add_daily_price_bar(
            DailyPriceBarWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_symbol="EXM",
                trading_date=date(2026, 7, 10),
                close=Decimal("99.99"),
                currency_code="USD",
                adjustment_type="UNADJUSTED",
                retrieved_at=AS_OF,
            )
        )
        action = repository.add_corporate_action(
            CorporateActionWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_action_id="tool-action",
                action_type="OTHER",
                status="UNKNOWN",
                retrieved_at=AS_OF,
            )
        )
        document = repository.add_source_document(
            SourceDocumentWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_document_id="tool-document",
                document_type="OTHER",
                title="Tool metadata",
                source_url="https://www.sec.gov/tool-document",
                storage_uri="blob://fixture/tool-document",
                document_status="AVAILABLE",
                retrieved_at=AS_OF,
            )
        )
        fact = repository.add_financial_fact(
            ProviderFinancialFactWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                document_id=document.id,
                statement_type="OTHER",
                provider_concept="raw:ToolFact",
                dimensions={},
                value=Decimal("12.5"),
                retrieved_at=AS_OF,
            )
        )
        snapshot = repository.add_snapshot(
            DataSnapshotWrite(
                security_id=SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=1,
                status="BUILDING",
                formula_version="raw-data-v1",
            )
        )
        price_item = repository.add_snapshot_item(
            SnapshotItemWrite(
                snapshot_id=snapshot.id,
                provider_id=ids["provider"],
                category="DAILY_PRICES",
                source_record_type="daily_price_bars",
                source_record_id=older_bar.id,
                retrieved_at=AS_OF,
                checksum_input="older-bar",
                checksum="b" * 64,
            )
        )
        repository.add_snapshot_item(
            SnapshotItemWrite(
                snapshot_id=snapshot.id,
                provider_id=ids["provider"],
                category="FINANCIAL_FACTS",
                source_record_type="provider_financial_facts",
                source_record_id=fact.id,
                retrieved_at=AS_OF,
                checksum_input="fact",
                checksum="c" * 64,
            )
        )
        repository.update_snapshot(
            snapshot.id,
            DataSnapshotUpdate(
                status="PARTIAL",
                completed_at=AS_OF,
                checksum="d" * 64,
            ),
        )
        session.commit()

        assert repository.list_daily_prices_by_ids(SECURITY_ID, (older_bar.id,)) == (older_bar,)
        assert newer_bar.id not in {
            record.id
            for record in repository.list_daily_prices_by_ids(SECURITY_ID, (older_bar.id,))
        }
        assert repository.list_corporate_actions_by_ids(SECURITY_ID, (action.id,)) == (action,)
        assert repository.list_financial_facts_by_ids(SECURITY_ID, (fact.id,)) == (fact,)
        assert repository.list_source_documents_by_ids(SECURITY_ID, (document.id,)) == (document,)
        assert repository.get_source_document_metadata(document.id, SECURITY_ID, AS_OF) == document
        assert repository.list_snapshot_items_by_category(
            snapshot.id, DataCategory.DAILY_PRICES, 100
        ) == (price_item,)


def test_tool_read_ports_are_bounded_and_project_no_provider_url_or_document_storage(
    repository_engine: Engine,
) -> None:
    statements: list[str] = []

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        document = repository.add_source_document(
            SourceDocumentWrite(
                security_id=SECURITY_ID,
                provider_id=ids["provider"],
                source_payload_id=ids["payload"],
                provider_document_id="safe-projection",
                document_type="OTHER",
                title="Safe projection",
                source_url="https://www.sec.gov/safe-projection",
                storage_uri="blob://fixture/safe-projection",
                document_status="AVAILABLE",
                retrieved_at=AS_OF,
            )
        )
        session.commit()
        event.listen(repository_engine, "before_cursor_execute", capture_statement)
        try:
            provenance = repository.list_provider_provenance((ids["provider"],))
            provider_select = statements[-1]
            documents = repository.list_source_documents_by_ids(SECURITY_ID, (document.id,))
            document_select = statements[-1]
        finally:
            event.remove(repository_engine, "before_cursor_execute", capture_statement)

    assert provenance[0].provider_type == "FIXTURE"
    assert documents == (document,)
    assert "base_url" not in provider_select
    assert "documentation_url" not in provider_select
    assert "storage_uri" not in document_select
    assert "LIMIT" in provider_select.upper()
    assert "LIMIT" in document_select.upper()

    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        with pytest.raises(ValueError, match="between 1 and 100"):
            repository.list_provider_provenance(tuple(UUID(int=value) for value in range(101)))
        with pytest.raises(ValueError, match="between 1 and 100"):
            repository.list_daily_prices_by_ids(
                SECURITY_ID,
                tuple(UUID(int=value + 1000) for value in range(101)),
            )


def test_whole_snapshot_aggregate_reads_all_items_without_relaxing_public_limit(
    repository_engine: Engine,
) -> None:
    statements: list[str] = []

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    with Session(repository_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        ids = _write_complete_lineage(repository)
        live_provider = repository.add_provider(
            DataProviderWrite(
                code="LIVE_AGGREGATE",
                name="Live aggregate provider",
                provider_type="MARKET_DATA",
                status="APPROVED",
                terms_status="VERIFIED",
                capabilities=("DAILY_PRICES",),
            )
        )
        fixture_provider_ids = [ids["provider"]]
        for index in range(99):
            fixture_provider_ids.append(
                repository.add_provider(
                    DataProviderWrite(
                        code=f"FIXTURE_AGGREGATE_{index:02d}",
                        name=f"Fixture aggregate provider {index}",
                        provider_type="FIXTURE",
                        status="APPROVED",
                        terms_status="VERIFIED",
                        capabilities=("DAILY_PRICES",),
                    )
                ).id
            )
        older = AS_OF.replace(hour=17)
        later = AS_OF.replace(hour=19)
        mixed_snapshot = repository.add_snapshot(
            DataSnapshotWrite(
                security_id=SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=10,
                status="BUILDING",
                formula_version="raw-data-v1",
            )
        )
        for index in range(121):
            provider_id = (
                live_provider.id
                if index == 120
                else fixture_provider_ids[index % len(fixture_provider_ids)]
            )
            retrieved_at = later if index == 120 else older
            repository.add_snapshot_item(
                SnapshotItemWrite(
                    snapshot_id=mixed_snapshot.id,
                    provider_id=provider_id,
                    category="DAILY_PRICES",
                    source_record_type="daily_price_bars",
                    source_record_id=UUID(int=10000 + index),
                    source_published_at=retrieved_at,
                    retrieved_at=retrieved_at,
                    checksum_input=f"mixed-{index}",
                    checksum=f"{index:064x}",
                )
            )
        repository.update_snapshot(
            mixed_snapshot.id,
            DataSnapshotUpdate(
                status="COMPLETE",
                completed_at=AS_OF,
                checksum="a" * 64,
            ),
        )
        fixture_snapshot = repository.add_snapshot(
            DataSnapshotWrite(
                security_id=SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=11,
                status="BUILDING",
                formula_version="raw-data-v1",
            )
        )
        for index in range(121):
            repository.add_snapshot_item(
                SnapshotItemWrite(
                    snapshot_id=fixture_snapshot.id,
                    provider_id=ids["provider"],
                    category="DAILY_PRICES",
                    source_record_type="daily_price_bars",
                    source_record_id=UUID(int=20000 + index),
                    source_published_at=older,
                    retrieved_at=older,
                    checksum_input=f"fixture-{index}",
                    checksum=f"{index + 1000:064x}",
                )
            )
        repository.update_snapshot(
            fixture_snapshot.id,
            DataSnapshotUpdate(
                status="COMPLETE",
                completed_at=AS_OF,
                checksum="b" * 64,
            ),
        )
        overflow_snapshot = repository.add_snapshot(
            DataSnapshotWrite(
                security_id=SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=12,
                status="BUILDING",
                formula_version="raw-data-v1",
            )
        )
        for index in range(397):
            repository.add_snapshot_item(
                SnapshotItemWrite(
                    snapshot_id=overflow_snapshot.id,
                    provider_id=ids["provider"],
                    category="DAILY_PRICES",
                    source_record_type="daily_price_bars",
                    source_record_id=UUID(int=30000 + index),
                    source_published_at=older,
                    retrieved_at=older,
                    checksum_input=f"overflow-{index}",
                    checksum=f"{index + 2000:064x}",
                )
            )
        session.commit()

        event.listen(repository_engine, "before_cursor_execute", capture_statement)
        try:
            mixed = repository.get_snapshot_evidence_aggregate(mixed_snapshot.id)
            aggregate_select = statements[-1]
            fixture = repository.get_snapshot_evidence_aggregate(fixture_snapshot.id)
            overflow = repository.get_snapshot_evidence_aggregate(overflow_snapshot.id)
            public_items = repository.list_snapshot_items(mixed_snapshot.id, 100)
            registry = create_tool_registry(DataAccessQueryService(repository))
            mixed_output = registry.execute(
                "get_data_snapshot",
                "1.0.0",
                {"snapshot_id": mixed_snapshot.id},
            )
            fixture_output = registry.execute(
                "get_data_snapshot",
                "1.0.0",
                {"snapshot_id": fixture_snapshot.id},
            )
            overflow_output = registry.execute(
                "get_data_snapshot",
                "1.0.0",
                {"snapshot_id": overflow_snapshot.id},
            )
        finally:
            event.remove(repository_engine, "before_cursor_execute", capture_statement)

    assert isinstance(mixed, SnapshotEvidenceAggregateRecord)
    assert mixed.item_count == 121
    assert mixed.provider_ids == tuple(sorted((*fixture_provider_ids, live_provider.id), key=str))
    assert len(mixed.provider_ids) == 101
    assert mixed.latest_retrieved_at == later
    assert isinstance(fixture, SnapshotEvidenceAggregateRecord)
    assert fixture.item_count == 121
    assert fixture.provider_ids == (ids["provider"],)
    assert fixture.latest_retrieved_at == older
    assert overflow is None
    assert len(public_items) == 100
    assert mixed_output.provenance.data_origin == "MIXED"
    assert mixed_output.retrieved_at == later
    assert fixture_output.provenance.model_dump(mode="json") == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }
    assert overflow_output.status == "FAIL"
    assert overflow_output.provenance.data_origin == "UNKNOWN"
    assert "SNAPSHOT_AGGREGATION_UNAVAILABLE" in overflow_output.warnings
    lowered = aggregate_select.lower()
    assert "having" in lowered
    assert "source_record_id" not in lowered
    assert "checksum" not in lowered
    assert "storage_uri" not in lowered
    assert "inline_json" not in lowered
    provider_selects = tuple(
        statement
        for statement in statements
        if "from data_providers" in statement.lower()
        and "provider_type" in statement.lower()
        and "limit" in statement.lower()
    )
    assert len(provider_selects) == 3
