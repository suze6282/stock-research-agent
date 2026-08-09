from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Lock, Thread
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.orm import Session

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.models import (
    DailyPriceBar,
    IngestionRun,
    ProviderRequestLog,
    RawPayload,
)
from stock_research_agent.db.repositories.data_access import SqlAlchemyDataAccessRepository
from stock_research_agent.domain.data_access.enums import (
    AccessMode,
    DataCategory,
    DataOrigin,
    LiveStatus,
    ProviderCapability,
    ProviderStatus,
    QualityStatus,
)
from stock_research_agent.domain.data_access.ingestion import IngestionRequest, IngestionService
from stock_research_agent.domain.data_access.schemas import (
    DataProviderWrite,
    DataQuality,
    ProviderDescriptor,
    ProviderEnvelope,
    ProviderInstrumentMappingWrite,
    ProviderRecord,
    ProviderRequest,
)
from stock_research_agent.infrastructure.blob_storage import BlobMetadata, InMemoryBlobStorage
from stock_research_agent.providers.registry import ProviderRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
SECURITY_ID = UUID("40000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 7, 15, 8, 30, tzinfo=UTC)


def _integration_was_explicitly_selected() -> bool:
    arguments = [argument.replace("\\", "/").lower() for argument in sys.argv[1:]]
    return any("tests/integration" in argument for argument in arguments)


if TEST_DATABASE_URL is None and _integration_was_explicitly_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for PostgreSQL ingestion tests")


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture
def ingestion_engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
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
                VALUES ('10000000-0000-0000-0000-000000000001', 'US_EQUITY',
                        'US Equity', 'US', 'USD', 'ACTIVE');
                INSERT INTO exchanges
                    (id, market_id, mic, name, short_name, country_code, timezone,
                     default_currency_code, status)
                VALUES ('20000000-0000-0000-0000-000000000001',
                        '10000000-0000-0000-0000-000000000001', 'XNAS', 'Nasdaq',
                        'Nasdaq', 'US', 'America/New_York', 'USD', 'ACTIVE');
                INSERT INTO issuers
                    (id, legal_name, normalized_legal_name, display_name,
                     normalized_display_name, country_code, issuer_status)
                VALUES ('30000000-0000-0000-0000-000000000001', 'Example Inc.',
                        'EXAMPLE INC', 'Example', 'EXAMPLE', 'US', 'ACTIVE');
                INSERT INTO securities
                    (id, issuer_id, exchange_id, symbol, normalized_symbol,
                     display_name, security_type, currency_code, listing_status,
                     is_primary_listing)
                VALUES ('40000000-0000-0000-0000-000000000001',
                        '30000000-0000-0000-0000-000000000001',
                        '20000000-0000-0000-0000-000000000001', 'EXM', 'EXM',
                        'Example', 'COMMON_STOCK', 'USD', 'ACTIVE', true)
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


class IncrementingClock:
    def __init__(self) -> None:
        self._value = NOW
        self._lock = Lock()

    def now(self) -> datetime:
        with self._lock:
            value = self._value
            self._value += timedelta(microseconds=1)
            return value


class PgFixtureAdapter:
    code = "PG_FIXTURE"
    version = "1.0.0"
    capabilities = frozenset(
        {
            ProviderCapability.DAILY_PRICES,
            ProviderCapability.FINANCIAL_FACTS,
            ProviderCapability.FILING_METADATA,
        }
    )
    descriptor = ProviderDescriptor(
        code=code,
        name="PostgreSQL fixture adapter",
        version=version,
        status=ProviderStatus.APPROVED,
        capabilities=capabilities,
        is_enabled=True,
        requires_credentials=False,
        credentials_configured=False,
    )

    def __init__(
        self,
        *,
        payload: bytes = b'{"revision":1}\n',
        invalid_price: bool = False,
        quality_override: QualityStatus | None = None,
        malformed_filing: bool = False,
        provider_request_id: str | None = "pg-request:123",
    ):
        self.payload = payload
        self.invalid_price = invalid_price
        self.quality_override = quality_override
        self.malformed_filing = malformed_filing
        self.provider_request_id = provider_request_id
        self.fetch_count = 0
        self._lock = Lock()

    def fetch(self, request: ProviderRequest) -> ProviderEnvelope:
        with self._lock:
            self.fetch_count += 1
        if request.category is DataCategory.FILING_METADATA:
            records = (
                ProviderRecord(
                    record_type="filing_metadata",
                    provider_record_id="0001-26-000001",
                    source_published_at=NOW,
                    data=(
                        {
                            "document_type": "SEC_10_Q",
                            "accession_number": "0001-26-000001",
                            "document_status": "METADATA_ONLY",
                        }
                        if self.malformed_filing
                        else {
                            "document_type": "SEC_10_Q",
                            "title": "Form 10-Q",
                            "source_url": "https://www.sec.gov/Archives/example.htm",
                            "document_status": "METADATA_ONLY",
                        }
                    ),
                ),
            )
            quality = self.quality_override or QualityStatus.PASS
            warnings = ()
        elif request.category is DataCategory.FINANCIAL_FACTS:
            records: tuple[ProviderRecord, ...] = ()
            quality = QualityStatus.PARTIAL
            warnings = ("FINANCIAL_FACTS_NOT_PRESERVED",)
        else:
            high = Decimal("9") if self.invalid_price else Decimal("11.000")
            records = (
                ProviderRecord(
                    record_type="daily_price",
                    provider_record_id=None,
                    source_published_at=None,
                    data={
                        "trading_date": "2026-07-10",
                        "open": Decimal("10.100"),
                        "high": high,
                        "low": Decimal("10.000"),
                        "close": Decimal("10.250"),
                        "volume": 123456789,
                        "currency_code": "USD",
                    },
                ),
            )
            quality = QualityStatus.PASS
            warnings = ()
        if self.quality_override is not None:
            quality = self.quality_override
        return ProviderEnvelope(
            provider_code=self.code,
            provider_version=self.version,
            category=request.category,
            records=records,
            raw_payload=self.payload,
            content_type="application/json",
            source_endpoint="fixture://postgres/pg_fixture.json",
            provider_request_id=self.provider_request_id,
            retrieved_at=NOW,
            source_published_at=None,
            warnings=warnings,
            quality=DataQuality(
                status=quality,
                required_fields_present=1 if records else 0,
                required_fields_total=1,
                missing_fields=() if records else ("financial_facts",),
                warnings=warnings,
            ),
            data_origin=DataOrigin.FIXTURE,
            access_mode=AccessMode.OFFLINE,
            live_status=LiveStatus.NOT_LIVE,
        )


class RecordingBlobStorage:
    def __init__(self) -> None:
        self.backend = InMemoryBlobStorage(max_blob_bytes=1024 * 1024)
        self.put_uris: list[str] = []
        self.deleted_uris: list[str] = []

    def put(
        self, data: bytes, *, content_type: str, metadata: dict[str, str] | None = None
    ) -> BlobMetadata:
        result = self.backend.put(data, content_type=content_type, metadata=metadata)
        self.put_uris.append(result.uri)
        return result

    def get(self, uri: str) -> bytes:
        return self.backend.get(uri)

    def exists(self, uri: str) -> bool:
        return self.backend.exists(uri)

    def delete(self, uri: str) -> None:
        self.backend.delete(uri)
        self.deleted_uris.append(uri)

    def checksum(self, uri: str) -> str:
        return self.backend.checksum(uri)

    def metadata(self, uri: str) -> BlobMetadata:
        return self.backend.metadata(uri)


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


def _seed_provider(repository: SqlAlchemyDataAccessRepository) -> None:
    provider = repository.add_provider(
        DataProviderWrite(
            code="PG_FIXTURE",
            name="PostgreSQL fixture adapter",
            provider_type="FIXTURE",
            status="APPROVED",
            base_url="https://fixtures.example.test/postgres",
            terms_status="VERIFIED",
            capabilities=("DAILY_PRICES", "FINANCIAL_FACTS", "FILING_METADATA"),
        )
    )
    repository.add_provider_mapping(
        ProviderInstrumentMappingWrite(
            provider_id=provider.id,
            security_id=SECURITY_ID,
            provider_symbol="EXM",
            provider_exchange_code="XNAS",
            provider_instrument_id="pg-exm",
            valid_from=date(2020, 1, 1),
            is_primary=True,
            metadata={"origin": "fixture"},
            source_name="test fixture",
        )
    )


def _request(
    *,
    category: DataCategory = DataCategory.DAILY_PRICES,
    parser_version: str = "1.0.0",
) -> IngestionRequest:
    return IngestionRequest(
        request_id=uuid4(),
        security_id=SECURITY_ID,
        provider_code="PG_FIXTURE",
        category=category,
        research_as_of_time=NOW,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 15),
        parameters={"source": "fixture"},
        parser_version=parser_version,
        schema_version="1.0.0",
    )


def _registry(adapter: PgFixtureAdapter) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(adapter)
    return registry


def test_first_repeat_lineage_pass_partial_and_caller_owned_session(
    ingestion_engine: Engine,
) -> None:
    seed_session = Session(ingestion_engine)
    _seed_provider(SqlAlchemyDataAccessRepository(seed_session))
    seed_session.commit()
    seed_session.close()

    adapter = PgFixtureAdapter()
    blobs = RecordingBlobStorage()
    session = SessionLifecycleSpy(bind=ingestion_engine)
    try:
        repository = SqlAlchemyDataAccessRepository(session)
        service = IngestionService(repository, _registry(adapter), blobs, clock=IncrementingClock())
        first_request = _request()
        first = service.ingest(first_request)
        repeated = service.ingest(_request())
        partial = service.ingest(_request(category=DataCategory.FINANCIAL_FACTS))

        assert first.status == "PASS" and repeated.run_id == first.run_id
        assert partial.status == "PARTIAL" and partial.records_stored == 0
        assert adapter.fetch_count == 2
        assert session.commit_calls == session.rollback_calls == session.close_calls == 0

        run = session.get(IngestionRun, first.run_id)
        request_log = session.scalar(
            select(ProviderRequestLog).where(ProviderRequestLog.ingestion_run_id == first.run_id)
        )
        payload = session.scalar(
            select(RawPayload).where(RawPayload.ingestion_run_id == first.run_id)
        )
        price = session.scalar(
            select(DailyPriceBar).where(DailyPriceBar.source_payload_id == payload.id)
        )
        assert run is not None and request_log is not None and payload is not None
        assert price is not None
        assert payload.provider_request_log_id == request_log.id
        assert request_log.ingestion_run_id == run.id
        assert request_log.caller_request_id == first_request.request_id
        assert request_log.provider_request_id == "pg-request:123"
        assert price.close == Decimal("10.250000000000")
        assert price.volume == 123456789
        assert price.adjustment_type is None
        assert blobs.get(payload.storage_uri) == b'{"revision":1}\n'
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 2
        assert session.scalar(select(func.count()).select_from(ProviderRequestLog)) == 2
        assert session.scalar(select(func.count()).select_from(RawPayload)) == 2
        assert session.scalar(select(func.count()).select_from(DailyPriceBar)) == 1
        session.commit()
    finally:
        session.close()
    assert session.commit_calls == 1 and session.close_calls == 1


def test_concurrent_identical_ingestion_converges_on_one_lineage(
    ingestion_engine: Engine,
) -> None:
    with Session(ingestion_engine) as session:
        _seed_provider(SqlAlchemyDataAccessRepository(session))
        session.commit()

    adapter = PgFixtureAdapter()
    registry = _registry(adapter)
    blobs = RecordingBlobStorage()
    barrier = Barrier(2)
    results: list[object] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            with Session(ingestion_engine) as session:
                service = IngestionService(
                    SqlAlchemyDataAccessRepository(session),
                    registry,
                    blobs,
                    clock=IncrementingClock(),
                )
                barrier.wait()
                results.append(service.ingest(_request()))
                session.commit()
        except BaseException as error:
            errors.append(error)

    threads = [Thread(target=worker), Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert not any(thread.is_alive() for thread in threads)
    assert errors == [] and len(results) == 2
    assert len({result.run_id for result in results}) == 1
    assert adapter.fetch_count == 1
    with Session(ingestion_engine) as session:
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 1
        assert session.scalar(select(func.count()).select_from(ProviderRequestLog)) == 1
        assert session.scalar(select(func.count()).select_from(RawPayload)) == 1
        assert session.scalar(select(func.count()).select_from(DailyPriceBar)) == 1


def test_projection_failure_rolls_back_attempt_and_compensates_blob(
    ingestion_engine: Engine,
) -> None:
    with Session(ingestion_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        _seed_provider(repository)
        session.commit()
        adapter = PgFixtureAdapter(payload=b"failed-revision", invalid_price=True)
        blobs = RecordingBlobStorage()
        result = IngestionService(
            repository, _registry(adapter), blobs, clock=IncrementingClock()
        ).ingest(_request())
        assert result.status == "FAIL" and result.error_code == "PERSISTENCE_FAILED"
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 1
        assert session.scalar(select(func.count()).select_from(ProviderRequestLog)) == 0
        assert session.scalar(select(func.count()).select_from(RawPayload)) == 0
        assert session.scalar(select(func.count()).select_from(DailyPriceBar)) == 0
        assert blobs.put_uris == blobs.deleted_uris
        assert all(not blobs.exists(uri) for uri in blobs.put_uris)
        session.commit()


@pytest.mark.parametrize("quality", (QualityStatus.BLOCKED, QualityStatus.FAIL))
def test_nonpassing_quality_persists_raw_lineage_without_category_rows(
    ingestion_engine: Engine,
    quality: QualityStatus,
) -> None:
    with Session(ingestion_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        _seed_provider(repository)
        session.commit()
        adapter = PgFixtureAdapter(quality_override=quality)
        result = IngestionService(
            repository, _registry(adapter), RecordingBlobStorage(), clock=IncrementingClock()
        ).ingest(_request())

        assert result.status == quality.value
        assert result.records_received == 1 and result.records_stored == 0
        assert session.scalar(select(func.count()).select_from(ProviderRequestLog)) == 1
        assert session.scalar(select(func.count()).select_from(RawPayload)) == 1
        assert session.scalar(select(func.count()).select_from(DailyPriceBar)) == 0
        session.commit()


def test_malformed_filing_rolls_back_real_transaction_and_compensates_blob(
    ingestion_engine: Engine,
) -> None:
    with Session(ingestion_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        _seed_provider(repository)
        session.commit()
        adapter = PgFixtureAdapter(malformed_filing=True, payload=b"malformed-filing")
        blobs = RecordingBlobStorage()
        result = IngestionService(
            repository, _registry(adapter), blobs, clock=IncrementingClock()
        ).ingest(_request(category=DataCategory.FILING_METADATA))

        assert result.status == "FAIL" and result.error_code == "PERSISTENCE_FAILED"
        assert session.scalar(select(func.count()).select_from(ProviderRequestLog)) == 0
        assert session.scalar(select(func.count()).select_from(RawPayload)) == 0
        assert blobs.put_uris == blobs.deleted_uris
        assert blobs.put_uris and all(not blobs.exists(uri) for uri in blobs.put_uris)
        session.commit()


def test_corrected_lineage_coexists_and_raw_payload_is_immutable(
    ingestion_engine: Engine,
) -> None:
    with Session(ingestion_engine) as session:
        repository = SqlAlchemyDataAccessRepository(session)
        _seed_provider(repository)
        session.commit()

        first_adapter = PgFixtureAdapter(payload=b'{"revision":1}\n')
        blobs = RecordingBlobStorage()
        first = IngestionService(
            repository, _registry(first_adapter), blobs, clock=IncrementingClock()
        ).ingest(_request(parser_version="1.0.0"))
        session.commit()

        corrected_adapter = PgFixtureAdapter(payload=b'{"revision":2}\n')
        corrected = IngestionService(
            repository, _registry(corrected_adapter), blobs, clock=IncrementingClock()
        ).ingest(_request(parser_version="1.0.1"))
        session.commit()

        assert first.run_id != corrected.run_id
        payloads = session.scalars(select(RawPayload).order_by(RawPayload.created_at)).all()
        prices = session.scalars(select(DailyPriceBar).order_by(DailyPriceBar.created_at)).all()
        assert len(payloads) == len(prices) == 2
        assert payloads[0].id != payloads[1].id
        assert {price.source_payload_id for price in prices} == {payload.id for payload in payloads}
        assert {blobs.get(payload.storage_uri) for payload in payloads} == {
            b'{"revision":1}\n',
            b'{"revision":2}\n',
        }
        immutable_identity = tuple(
            (payload.id, payload.storage_uri, payload.checksum) for payload in payloads
        )
        immutable_price_ids = tuple(price.id for price in prices)

        replay_adapter = PgFixtureAdapter(payload=b'{"attempted-overwrite":true}\n')
        replay = IngestionService(
            repository, _registry(replay_adapter), blobs, clock=IncrementingClock()
        ).ingest(_request(parser_version="1.0.0"))
        assert replay.run_id == first.run_id and replay_adapter.fetch_count == 0
        assert session.scalar(select(func.count()).select_from(RawPayload)) == 2
        assert session.scalar(select(func.count()).select_from(DailyPriceBar)) == 2
        replayed_payloads = session.scalars(
            select(RawPayload).order_by(RawPayload.created_at)
        ).all()
        replayed_prices = session.scalars(
            select(DailyPriceBar).order_by(DailyPriceBar.created_at)
        ).all()
        assert (
            tuple(
                (payload.id, payload.storage_uri, payload.checksum) for payload in replayed_payloads
            )
            == immutable_identity
        )
        assert tuple(price.id for price in replayed_prices) == immutable_price_ids
        assert {blobs.get(payload.storage_uri) for payload in payloads} == {
            b'{"revision":1}\n',
            b'{"revision":2}\n',
        }
