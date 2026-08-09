from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Thread
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.models import DataSnapshot, SnapshotItem
from stock_research_agent.db.repositories.data_access import SqlAlchemyDataAccessRepository
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.domain.data_access.enums import DataCategory
from stock_research_agent.domain.data_access.ingestion import IngestionRequest, IngestionService
from stock_research_agent.domain.data_access.schemas import (
    DailyPriceBarWrite,
    DataProviderWrite,
    DataSnapshotUpdate,
    DataSnapshotWrite,
    ProviderFinancialFactWrite,
    ProviderInstrumentMappingWrite,
    SnapshotItemRecord,
    SnapshotItemWrite,
)
from stock_research_agent.domain.data_access.snapshots import (
    SnapshotBuilder,
    SnapshotBuildError,
    SnapshotBuildRequest,
    SnapshotErrorCode,
)
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_SECURITY_ID,
    MICRON_SECURITY_ID,
    SecurityMasterSeedService,
)
from stock_research_agent.infrastructure.blob_storage import InMemoryBlobStorage
from stock_research_agent.providers.fixtures.provider import create_stage1_fixture_registry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
AS_OF = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
RETRIEVED_AT = datetime(2026, 7, 11, 12, 25, tzinfo=UTC)


def _integration_was_explicitly_selected() -> bool:
    arguments = [argument.replace("\\", "/").lower() for argument in sys.argv[1:]]
    return any("tests/integration" in argument for argument in arguments)


if TEST_DATABASE_URL is None and _integration_was_explicitly_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for PostgreSQL snapshot tests")


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


class FixedClock:
    def __init__(self, value: datetime = RETRIEVED_AT) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


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


@pytest.fixture
def snapshot_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
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
    try:
        yield engine
    finally:
        engine.dispose()
        if previous is None:
            monkeypatch.delenv("DATABASE_URL", raising=False)
        else:
            monkeypatch.setenv("DATABASE_URL", previous)


def _seed_samples(session: Session) -> dict[str, UUID]:
    SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
    repository = SqlAlchemyDataAccessRepository(session)
    definitions = (
        (
            "STAGE1_SSE_FIXTURE",
            "Stage 1 SSE evidence fixture",
            "EXPERIMENTAL",
            ("DAILY_PRICES",),
            INDUSTRIAL_FII_SECURITY_ID,
            "TEST001",
            "XSHG",
        ),
        (
            "STAGE1_NASDAQ_FIXTURE",
            "Stage 1 Nasdaq evidence fixture",
            "EXPERIMENTAL",
            ("DAILY_PRICES",),
            MICRON_SECURITY_ID,
            "TSTX",
            "XNAS",
        ),
    )
    provider_ids: dict[str, UUID] = {}
    for code, name, status, capabilities, security_id, symbol, exchange_code in definitions:
        provider = repository.add_provider(
            DataProviderWrite(
                code=code,
                name=name,
                provider_type="FIXTURE",
                status=status,
                terms_status="NEEDS_REVIEW",
                capabilities=capabilities,
            )
        )
        provider_ids[code] = provider.id
        repository.add_provider_mapping(
            ProviderInstrumentMappingWrite(
                provider_id=provider.id,
                security_id=security_id,
                provider_symbol=symbol,
                provider_exchange_code=exchange_code,
                valid_from=date(2020, 1, 1),
                is_primary=True,
                metadata={"origin": "verified_stage1_fixture"},
                source_name="Stage 1 verified fixture manifest",
            )
        )
    session.flush()
    return provider_ids


def _ingest_price(session: Session, *, security_id: UUID, provider_code: str) -> None:
    clock = FixedClock()
    result = IngestionService(
        SqlAlchemyDataAccessRepository(session),
        create_stage1_fixture_registry(clock=clock),
        InMemoryBlobStorage(max_blob_bytes=1024 * 1024),
        clock=clock,
    ).ingest(
        IngestionRequest(
            request_id=uuid4(),
            security_id=security_id,
            provider_code=provider_code,
            category=DataCategory.DAILY_PRICES,
            research_as_of_time=AS_OF,
            date_from=date(2026, 1, 15),
            date_to=date(2026, 1, 15),
            parameters={"mode": "offline_fixture"},
            parser_version="1.0.0",
            schema_version="1.0.0",
        )
    )
    assert result.status == "PARTIAL"
    assert result.records_stored == 1


def _seed_and_ingest(session: Session) -> dict[str, UUID]:
    provider_ids = _seed_samples(session)
    _ingest_price(
        session,
        security_id=INDUSTRIAL_FII_SECURITY_ID,
        provider_code="STAGE1_SSE_FIXTURE",
    )
    _ingest_price(
        session,
        security_id=MICRON_SECURITY_ID,
        provider_code="STAGE1_NASDAQ_FIXTURE",
    )
    session.flush()
    return provider_ids


def _request(
    security_id: UUID = MICRON_SECURITY_ID,
    *,
    snapshot_version: int = 1,
    categories: tuple[DataCategory, ...] = (DataCategory.DAILY_PRICES,),
    provider_preference: tuple[UUID, ...] = (),
    item_limit: int = 10,
) -> SnapshotBuildRequest:
    return SnapshotBuildRequest(
        security_id=security_id,
        research_as_of_time=AS_OF,
        snapshot_version=snapshot_version,
        categories=categories,
        exchange_timezone=(
            "Asia/Shanghai" if security_id == INDUSTRIAL_FII_SECURITY_ID else "America/New_York"
        ),
        provider_preference=provider_preference,
        item_limit=item_limit,
    )


def test_first_build_replay_and_caller_owned_session(snapshot_engine: Engine) -> None:
    session = SessionLifecycleSpy(bind=snapshot_engine)
    try:
        provider_ids = _seed_and_ingest(session)
        builder = SnapshotBuilder(
            SqlAlchemyDataAccessRepository(session), clock=FixedClock(AS_OF + timedelta(minutes=1))
        )
        request = _request(provider_preference=(provider_ids["STAGE1_NASDAQ_FIXTURE"],))

        first = builder.build(request)
        replay = builder.build(request)

        assert first == replay
        assert first.status == "PARTIAL"
        assert len(first.items) == 1
        assert first.warnings[0].startswith("UNKNOWN_PUBLICATION:DAILY_PRICES:")
        assert session.commit_calls == session.rollback_calls == session.close_calls == 0
        session.commit()
    finally:
        session.close()
    assert session.commit_calls == 1 and session.close_calls == 1


def test_concurrent_identical_builds_converge(snapshot_engine: Engine) -> None:
    with Session(snapshot_engine) as session:
        _seed_and_ingest(session)
        session.commit()

    barrier = Barrier(2)
    results: list[object] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            with Session(snapshot_engine) as session:
                barrier.wait()
                result = SnapshotBuilder(
                    SqlAlchemyDataAccessRepository(session),
                    clock=FixedClock(AS_OF + timedelta(minutes=1)),
                ).build(_request())
                session.commit()
                results.append(result)
        except BaseException as error:
            errors.append(error)

    threads = [Thread(target=worker), Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == [] and len(results) == 2
    assert len({result.snapshot.id for result in results}) == 1
    with Session(snapshot_engine) as session:
        assert session.scalar(select(func.count()).select_from(DataSnapshot)) == 1
        assert session.scalar(select(func.count()).select_from(SnapshotItem)) == 1


def test_terminal_snapshot_and_items_are_database_immutable(snapshot_engine: Engine) -> None:
    with Session(snapshot_engine) as session:
        _seed_and_ingest(session)
        result = SnapshotBuilder(
            SqlAlchemyDataAccessRepository(session), clock=FixedClock(AS_OF + timedelta(minutes=1))
        ).build(_request())
        session.commit()

        statements = (
            text("UPDATE data_snapshots SET notes = 'changed' WHERE id = :id"),
            text("DELETE FROM data_snapshots WHERE id = :id"),
            text("UPDATE snapshot_items SET checksum = :checksum WHERE snapshot_id = :id"),
            text("DELETE FROM snapshot_items WHERE snapshot_id = :id"),
            text(
                """
                INSERT INTO snapshot_items
                    (id, snapshot_id, provider_id, category, source_record_type,
                     source_record_id, source_published_at, retrieved_at,
                     checksum_input, checksum)
                SELECT :new_id, :id, provider_id, category, source_record_type,
                       source_record_id, source_published_at, retrieved_at,
                       checksum_input, checksum
                FROM snapshot_items WHERE snapshot_id = :id LIMIT 1
                """
            ),
        )
        for statement in statements:
            with pytest.raises(DBAPIError), session.begin_nested():
                session.execute(
                    statement,
                    {
                        "id": result.snapshot.id,
                        "new_id": uuid4(),
                        "checksum": "0" * 64,
                    },
                )


def test_building_item_as_of_guards_and_complete_guard(snapshot_engine: Engine) -> None:
    with Session(snapshot_engine) as session:
        _seed_and_ingest(session)
        repository = SqlAlchemyDataAccessRepository(session)
        with pytest.raises(DBAPIError), session.begin_nested():
            repository.add_snapshot(
                DataSnapshotWrite(
                    security_id=MICRON_SECURITY_ID,
                    research_as_of_time=AS_OF,
                    snapshot_version=6,
                    status="PARTIAL",
                    completed_at=AS_OF + timedelta(minutes=1),
                    checksum="0" * 64,
                    formula_version="raw-data-v1",
                )
            )
        price = repository.list_daily_history(MICRON_SECURITY_ID, AS_OF, date(2026, 7, 15), 1)[0]
        building = repository.add_snapshot(
            DataSnapshotWrite(
                security_id=MICRON_SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=7,
                status="BUILDING",
                formula_version="raw-data-v1",
            )
        )
        checksum_input = '{"schema":"snapshot-item-v1"}'
        checksum = hashlib.sha256(checksum_input.encode()).hexdigest()

        for field, future in (
            ("retrieved_at", AS_OF + timedelta(seconds=1)),
            ("source_published_at", AS_OF + timedelta(seconds=1)),
        ):
            values = {
                "snapshot_id": building.id,
                "provider_id": price.provider_id,
                "category": DataCategory.DAILY_PRICES,
                "source_record_type": "daily_price_bars",
                "source_record_id": price.id,
                "source_published_at": AS_OF - timedelta(seconds=1),
                "retrieved_at": AS_OF - timedelta(seconds=1),
                "checksum_input": checksum_input,
                "checksum": checksum,
            }
            values[field] = future
            with pytest.raises(DBAPIError), session.begin_nested():
                repository.add_snapshot_item(SnapshotItemWrite.model_validate(values))

        repository.add_snapshot_item(
            SnapshotItemWrite(
                snapshot_id=building.id,
                provider_id=price.provider_id,
                category=DataCategory.DAILY_PRICES,
                source_record_type="daily_price_bars",
                source_record_id=price.id,
                source_published_at=None,
                retrieved_at=price.retrieved_at,
                checksum_input=checksum_input,
                checksum=checksum,
            )
        )
        with pytest.raises(DBAPIError), session.begin_nested():
            repository.update_snapshot(
                building.id,
                DataSnapshotUpdate(
                    status="COMPLETE",
                    completed_at=AS_OF + timedelta(minutes=1),
                    checksum="1" * 64,
                ),
            )


class FailingItemRepository(SqlAlchemyDataAccessRepository):
    def add_snapshot_item(self, value: SnapshotItemWrite) -> SnapshotItemRecord:
        raise RuntimeError("unsafe database details")


def test_build_failure_leaves_failed_without_checksum_or_items(snapshot_engine: Engine) -> None:
    with Session(snapshot_engine) as session:
        _seed_and_ingest(session)
        with pytest.raises(SnapshotBuildError) as captured:
            SnapshotBuilder(
                FailingItemRepository(session), clock=FixedClock(AS_OF + timedelta(minutes=1))
            ).build(_request())
        assert captured.value.code is SnapshotErrorCode.BUILD_FAILED
        assert str(captured.value) == "Snapshot build failed safely"
        snapshot = session.scalar(select(DataSnapshot))
        assert snapshot is not None
        assert snapshot.status == "FAILED" and snapshot.checksum is None
        assert session.scalar(select(func.count()).select_from(SnapshotItem)) == 0
        session.commit()


def test_new_evidence_requires_new_version(snapshot_engine: Engine) -> None:
    with Session(snapshot_engine) as session:
        _seed_samples(session)
        _ingest_price(
            session,
            security_id=MICRON_SECURITY_ID,
            provider_code="STAGE1_NASDAQ_FIXTURE",
        )
        builder = SnapshotBuilder(
            SqlAlchemyDataAccessRepository(session), clock=FixedClock(AS_OF + timedelta(minutes=1))
        )
        first = builder.build(_request())
        second_request = IngestionRequest(
            request_id=uuid4(),
            security_id=MICRON_SECURITY_ID,
            provider_code="STAGE1_NASDAQ_FIXTURE",
            category=DataCategory.DAILY_PRICES,
            research_as_of_time=AS_OF,
            date_from=date(2026, 1, 15),
            date_to=date(2026, 1, 15),
            parameters={"mode": "offline_fixture"},
            parser_version="1.0.1",
            schema_version="1.0.0",
        )
        result = IngestionService(
            SqlAlchemyDataAccessRepository(session),
            create_stage1_fixture_registry(clock=FixedClock()),
            InMemoryBlobStorage(max_blob_bytes=1024 * 1024),
            clock=FixedClock(),
        ).ingest(second_request)
        assert result.records_stored == 1

        with pytest.raises(SnapshotBuildError) as captured:
            builder.build(_request())
        assert captured.value.code is SnapshotErrorCode.VERSION_CONFLICT
        second = builder.build(_request(snapshot_version=2))
        assert second.snapshot.id != first.snapshot.id
        assert second.checksum != first.checksum
        assert len(second.items) == 2


def test_postgres_replay_returns_more_than_one_hundred_ordered_items(
    snapshot_engine: Engine,
) -> None:
    with Session(snapshot_engine) as session:
        _seed_samples(session)
        _ingest_price(
            session,
            security_id=MICRON_SECURITY_ID,
            provider_code="STAGE1_NASDAQ_FIXTURE",
        )
        repository = SqlAlchemyDataAccessRepository(session)
        retained = repository.list_daily_history(
            MICRON_SECURITY_ID,
            AS_OF,
            date(2026, 7, 15),
            1,
        )[0]
        for offset in range(60):
            repository.add_daily_price_bar(
                DailyPriceBarWrite(
                    security_id=MICRON_SECURITY_ID,
                    provider_id=retained.provider_id,
                    source_payload_id=retained.source_payload_id,
                    provider_symbol="TSTX",
                    trading_date=date(2026, 5, 1) + timedelta(days=offset),
                    close=Decimal(offset + 1),
                    volume=offset + 1,
                    currency_code="USD",
                    source_published_at=RETRIEVED_AT - timedelta(days=1),
                    retrieved_at=RETRIEVED_AT,
                )
            )
            repository.add_financial_fact(
                ProviderFinancialFactWrite(
                    security_id=MICRON_SECURITY_ID,
                    provider_id=retained.provider_id,
                    source_payload_id=retained.source_payload_id,
                    statement_type="OTHER",
                    provider_concept=f"test:fact:{offset:02d}",
                    dimensions={},
                    value=Decimal(offset + 1),
                    source_published_at=RETRIEVED_AT - timedelta(days=1),
                    retrieved_at=RETRIEVED_AT,
                )
            )
        builder = SnapshotBuilder(
            repository,
            clock=FixedClock(AS_OF + timedelta(minutes=1)),
        )
        request = _request(
            categories=(DataCategory.DAILY_PRICES, DataCategory.FINANCIAL_FACTS),
            item_limit=61,
        )

        first = builder.build(request)
        replay = builder.build(request)

        assert len(first.items) == 121
        assert replay == first
        assert len(repository.list_snapshot_items_for_replay(first.snapshot.id)) == 121
        with pytest.raises(ValueError, match="between 1 and 100"):
            repository.list_snapshot_items(first.snapshot.id, 101)


def test_both_verified_samples_build_honest_partial_snapshots(snapshot_engine: Engine) -> None:
    with Session(snapshot_engine) as session:
        _seed_and_ingest(session)
        builder = SnapshotBuilder(
            SqlAlchemyDataAccessRepository(session), clock=FixedClock(AS_OF + timedelta(minutes=1))
        )

        fii = builder.build(_request(INDUSTRIAL_FII_SECURITY_ID))
        micron = builder.build(_request(MICRON_SECURITY_ID))
        missing = builder.build(
            _request(
                INDUSTRIAL_FII_SECURITY_ID,
                snapshot_version=2,
                categories=(DataCategory.FINANCIAL_FACTS,),
            )
        )

        assert fii.status == micron.status == missing.status == "PARTIAL"
        assert len(fii.items) == len(micron.items) == 1
        assert missing.items == ()
        assert fii.warnings[0].startswith("UNKNOWN_PUBLICATION:")
        assert micron.warnings[0].startswith("UNKNOWN_PUBLICATION:")
        assert missing.warnings == ("MISSING_CATEGORY:FINANCIAL_FACTS",)


def test_migration_downgrade_upgrade_recreates_snapshot_triggers(
    snapshot_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))

    def trigger_names() -> set[str]:
        with snapshot_engine.connect() as connection:
            return set(
                connection.scalars(
                    text(
                        """
                        SELECT tgname FROM pg_trigger
                        WHERE NOT tgisinternal
                          AND tgrelid IN ('data_snapshots'::regclass, 'snapshot_items'::regclass)
                        """
                    )
                )
            )

    expected = {
        "trg_data_snapshots_immutable",
        "trg_snapshot_items_guard",
    }
    assert expected <= trigger_names()
    command.downgrade(config, "0002_create_security_master")
    with snapshot_engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.data_snapshots')")) is None
    command.upgrade(config, "0003_data_access_snapshots")
    assert expected <= trigger_names()
