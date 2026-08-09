from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.repositories.data_access import SqlAlchemyDataAccessRepository
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.domain.data_access.ingestion import IngestionService
from stock_research_agent.domain.data_access.schemas import (
    CorporateActionWrite,
    DailyPriceBarWrite,
    DataProviderWrite,
    DataSnapshotUpdate,
    DataSnapshotWrite,
    IngestionRunWrite,
    ProviderFinancialFactWrite,
    ProviderInstrumentMappingWrite,
    ProviderRequestLogWrite,
    RawPayloadWrite,
    SnapshotItemWrite,
    SourceDocumentWrite,
)
from stock_research_agent.domain.data_access.snapshots import SnapshotBuilder
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_SECURITY_ID,
    MICRON_SECURITY_ID,
    SecurityMasterSeedService,
)
from stock_research_agent.infrastructure.blob_storage import InMemoryBlobStorage, LocalBlobStorage
from stock_research_agent.main import create_app
from stock_research_agent.providers.fixtures.provider import (
    Stage1NasdaqFixtureProvider,
    Stage1SecFixtureProvider,
    Stage1SseFixtureProvider,
)
from stock_research_agent.providers.http_client import SafeHttpClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
AS_OF = datetime(2026, 7, 10, 20, tzinfo=UTC)
OLDER = AS_OF - timedelta(hours=2)
NEWER = AS_OF - timedelta(hours=1)
MISSING_ID = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def _lineage(
    repository: SqlAlchemyDataAccessRepository,
    *,
    code: str,
    security_id: UUID,
    symbol: str,
    exchange_code: str,
) -> dict[str, UUID]:
    provider = repository.add_provider(
        DataProviderWrite(
            code=code,
            name=f"{symbol} verified fixture",
            provider_type="FIXTURE",
            status="APPROVED",
            base_url="https://fixtures.example.test/private-base",
            documentation_url="https://fixtures.example.test/private-docs",
            terms_status="VERIFIED",
            capabilities=(
                "DAILY_PRICES",
                "CORPORATE_ACTIONS",
                "FINANCIAL_FACTS",
                "FILING_METADATA",
            ),
        )
    )
    repository.add_provider_mapping(
        ProviderInstrumentMappingWrite(
            provider_id=provider.id,
            security_id=security_id,
            provider_symbol=symbol,
            provider_exchange_code=exchange_code,
            valid_from=date(2020, 1, 1),
            is_primary=True,
            metadata={"origin": "verified_fixture"},
            source_name="Task 10 PostgreSQL contract fixture",
        )
    )
    run = repository.create_ingestion_run(
        IngestionRunWrite(
            provider_id=provider.id,
            security_id=security_id,
            category="DAILY_PRICES",
            research_as_of_time=AS_OF,
            idempotency_key=f"task10:{code.lower()}:20260710",
            requested_at=OLDER,
        )
    )
    request = repository.add_request_log(
        ProviderRequestLogWrite(
            ingestion_run_id=run.id,
            provider_id=provider.id,
            caller_request_id=UUID(int=provider.id.int + 100),
            provider_request_id=f"{code}:fixture-request",
            endpoint_name="fixture.persisted",
            method="GET",
            safe_url="https://fixtures.example.test/persisted",
            request_started_at=OLDER,
            response_received_at=OLDER,
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
            security_id=security_id,
            category="DAILY_PRICES",
            content_type="application/json",
            storage_uri=f"blob://task10/{code.lower()}",
            checksum=f"{provider.id.int % 16:x}" * 64,
            source_published_at=None,
            retrieved_at=OLDER,
            provider_version="1.0.0",
            parser_version="1.0.0",
            schema_version="1.0.0",
            byte_size=128,
        )
    )
    return {"provider": provider.id, "payload": payload.id}


def _seed_persisted_evidence(engine: Engine) -> dict[str, UUID]:
    with Session(engine) as session:
        SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
        repository = SqlAlchemyDataAccessRepository(session)
        micron = _lineage(
            repository,
            code="TASK10_MU_FIXTURE",
            security_id=MICRON_SECURITY_ID,
            symbol="MU",
            exchange_code="XNAS",
        )
        fii = _lineage(
            repository,
            code="TASK10_601138_FIXTURE",
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            symbol="601138",
            exchange_code="XSHG",
        )
        mu_old = repository.add_daily_price_bar(
            DailyPriceBarWrite(
                security_id=MICRON_SECURITY_ID,
                provider_id=micron["provider"],
                source_payload_id=micron["payload"],
                provider_symbol="MU",
                trading_date=date(2026, 7, 9),
                open=Decimal("119.100000000001"),
                high=Decimal("123.500000000001"),
                low=Decimal("118.000000000001"),
                close=Decimal("121.250000000001"),
                volume=123456,
                currency_code="USD",
                adjustment_type="UNADJUSTED",
                source_published_at=None,
                retrieved_at=OLDER,
            )
        )
        mu_new = repository.add_daily_price_bar(
            DailyPriceBarWrite(
                security_id=MICRON_SECURITY_ID,
                provider_id=micron["provider"],
                source_payload_id=micron["payload"],
                provider_symbol="MU",
                trading_date=date(2026, 7, 10),
                close=Decimal("130.750000000001"),
                volume=222222,
                currency_code="USD",
                adjustment_type="UNADJUSTED",
                source_published_at=NEWER,
                retrieved_at=NEWER,
            )
        )
        fii_price = repository.add_daily_price_bar(
            DailyPriceBarWrite(
                security_id=INDUSTRIAL_FII_SECURITY_ID,
                provider_id=fii["provider"],
                source_payload_id=fii["payload"],
                provider_symbol="601138",
                trading_date=date(2026, 7, 10),
                close=Decimal("21.880000000001"),
                volume=987654,
                currency_code="CNY",
                adjustment_type="UNADJUSTED",
                source_published_at=None,
                retrieved_at=OLDER,
            )
        )
        action = repository.add_corporate_action(
            CorporateActionWrite(
                security_id=MICRON_SECURITY_ID,
                provider_id=micron["provider"],
                source_payload_id=micron["payload"],
                provider_action_id="mu-dividend-2026",
                action_type="CASH_DIVIDEND",
                announcement_date=date(2026, 6, 25),
                ex_date=date(2026, 7, 8),
                cash_amount=Decimal("0.125000000001"),
                currency_code="USD",
                status="CONFIRMED",
                source_published_at=OLDER,
                retrieved_at=OLDER,
            )
        )
        document = repository.add_source_document(
            SourceDocumentWrite(
                security_id=MICRON_SECURITY_ID,
                provider_id=micron["provider"],
                source_payload_id=micron["payload"],
                provider_document_id="mu-10q-2026",
                document_type="SEC_10_Q",
                title="Micron quarterly filing metadata",
                form_type="10-Q",
                accession_number="000000-task10",
                period_end=date(2026, 5, 31),
                filed_at=OLDER,
                published_at=OLDER,
                source_url="https://www.sec.gov/Archives/example.htm",
                primary_document_name="example.htm",
                mime_type="text/html",
                storage_uri="blob://task10/secret-local-document",
                checksum="d" * 64,
                byte_size=4567,
                document_status="AVAILABLE",
                retrieved_at=OLDER,
            )
        )
        fact = repository.add_financial_fact(
            ProviderFinancialFactWrite(
                security_id=MICRON_SECURITY_ID,
                provider_id=micron["provider"],
                source_payload_id=micron["payload"],
                document_id=document.id,
                statement_type="INCOME_STATEMENT",
                provider_concept="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                reported_label="Revenue",
                taxonomy="us-gaap",
                context_id="task10-context",
                dimensions={"reported": True},
                value=Decimal("8123000000.123456789012"),
                unit="USD",
                currency_code="USD",
                fiscal_year=2026,
                fiscal_quarter=3,
                fiscal_period="Q3",
                period_start=date(2026, 3, 1),
                period_end=date(2026, 5, 31),
                filed_at=OLDER,
                source_published_at=OLDER,
                form_type="10-Q",
                is_annual=False,
                is_cumulative=True,
                is_audited=False,
                is_restated=False,
                provider_record_id="reported-revenue",
                retrieved_at=OLDER,
            )
        )
        snapshot = repository.add_snapshot(
            DataSnapshotWrite(
                security_id=MICRON_SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=1,
                status="BUILDING",
                formula_version="raw-data-v1",
            )
        )
        captured = (
            ("DAILY_PRICES", "daily_price_bars", mu_old.id, micron["provider"], None),
            (
                "CORPORATE_ACTIONS",
                "corporate_actions",
                action.id,
                micron["provider"],
                OLDER,
            ),
            (
                "FINANCIAL_FACTS",
                "provider_financial_facts",
                fact.id,
                micron["provider"],
                OLDER,
            ),
            (
                "FILING_METADATA",
                "source_documents",
                document.id,
                micron["provider"],
                OLDER,
            ),
        )
        for index, (category, source_type, source_id, provider_id, published_at) in enumerate(
            captured, start=1
        ):
            repository.add_snapshot_item(
                SnapshotItemWrite(
                    snapshot_id=snapshot.id,
                    provider_id=provider_id,
                    category=category,
                    source_record_type=source_type,
                    source_record_id=source_id,
                    source_published_at=published_at,
                    retrieved_at=OLDER,
                    checksum_input=f"task10:{index}:{source_id}",
                    checksum=f"{index:x}" * 64,
                )
            )
        repository.update_snapshot(
            snapshot.id,
            DataSnapshotUpdate(
                status="PARTIAL",
                completed_at=AS_OF,
                checksum="a" * 64,
                notes="Unknown publication retained",
            ),
        )
        fii_snapshot = repository.add_snapshot(
            DataSnapshotWrite(
                security_id=INDUSTRIAL_FII_SECURITY_ID,
                research_as_of_time=AS_OF,
                snapshot_version=1,
                status="BUILDING",
                formula_version="raw-data-v1",
            )
        )
        repository.add_snapshot_item(
            SnapshotItemWrite(
                snapshot_id=fii_snapshot.id,
                provider_id=fii["provider"],
                category="DAILY_PRICES",
                source_record_type="daily_price_bars",
                source_record_id=fii_price.id,
                source_published_at=None,
                retrieved_at=OLDER,
                checksum_input=f"task10:fii:{fii_price.id}",
                checksum="f" * 64,
            )
        )
        repository.update_snapshot(
            fii_snapshot.id,
            DataSnapshotUpdate(
                status="PARTIAL",
                completed_at=AS_OF,
                checksum="e" * 64,
                notes="Financial facts absent",
            ),
        )
        session.commit()
        return {
            "mu_provider": micron["provider"],
            "fii_provider": fii["provider"],
            "mu_old": mu_old.id,
            "mu_new": mu_new.id,
            "mu_snapshot": snapshot.id,
            "fii_snapshot": fii_snapshot.id,
            "fact": fact.id,
            "document": document.id,
        }


@pytest.fixture(scope="module")
def api_contract() -> Iterator[tuple[TestClient, dict[str, UUID], object]]:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(config, "head")
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=TEST_DATABASE_URL,
        api_prefix="/api/v1",
    )
    try:
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            empty_catalog = client.get(
                "/api/v1/data/providers",
                headers={"X-Request-ID": "empty-provider-catalog"},
            )
            ids = _seed_persisted_evidence(engine)
            yield client, ids, empty_catalog
    finally:
        engine.dispose()
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


def _scope() -> dict[str, str]:
    return {"research_as_of_time": AS_OF.isoformat()}


def _assert_safe_error(response: object, status_code: int, code: str) -> None:
    assert hasattr(response, "status_code") and hasattr(response, "json")
    assert response.status_code == status_code
    payload = response.json()
    assert payload["error"]["code"] == code
    assert response.headers["X-Request-ID"] == payload["error"]["request_id"]
    forbidden = ("SELECT ", "Traceback", "password=", "blob://", "C:\\", "/tmp/")
    assert not any(value in response.text for value in forbidden)


def test_provider_catalog_fixture_markers_and_empty_blocked(
    api_contract: tuple[TestClient, dict[str, UUID], object],
) -> None:
    client, _ids, empty_catalog = api_contract
    assert empty_catalog.status_code == 200
    assert empty_catalog.json()["status"] == "BLOCKED"
    assert empty_catalog.json()["warnings"] == ["NO_PROVIDERS_CONFIGURED"]
    response = client.get("/api/v1/data/providers")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PASS"
    assert len(payload["data"]) == 2
    assert payload["provenance"] == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }
    assert set(payload["data"][0]) == {
        "id",
        "code",
        "name",
        "provider_type",
        "status",
        "terms_status",
        "capabilities",
        "warnings",
        "provenance",
    }
    assert all(
        row["provenance"]
        == {
            "data_origin": "FIXTURE",
            "access_mode": "OFFLINE",
            "live_status": "NOT_LIVE",
        }
        and row["warnings"] == []
        for row in payload["data"]
    )
    assert "base_url" not in response.text and "documentation_url" not in response.text


def test_provider_catalog_mixed_rows_have_truthful_per_provider_markers(
    api_contract: tuple[TestClient, dict[str, UUID], object],
) -> None:
    client, _ids, _empty = api_contract
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with Session(engine) as session:
            repository = SqlAlchemyDataAccessRepository(session)
            repository.add_provider(
                DataProviderWrite(
                    code="TASK10_APPROVED_LIVE",
                    name="Approved persisted provider",
                    provider_type="MARKET_DATA",
                    status="APPROVED",
                    terms_status="VERIFIED",
                    capabilities=("DAILY_PRICES",),
                )
            )
            repository.add_provider(
                DataProviderWrite(
                    code="TASK10_UNVERIFIED_LIVE",
                    name="Unverified persisted provider",
                    provider_type="FILINGS",
                    status="NEEDS_CREDENTIALS",
                    terms_status="UNKNOWN",
                    capabilities=("FILING_METADATA",),
                )
            )
            session.commit()

        response = client.get("/api/v1/data/providers")
        assert response.status_code == 200
        payload = response.json()
        rows = {row["code"]: row for row in payload["data"]}
        assert payload["status"] == "PARTIAL"
        assert payload["provenance"] == {
            "data_origin": "MIXED",
            "access_mode": "MIXED",
            "live_status": "MIXED",
        }
        assert rows["TASK10_MU_FIXTURE"]["provenance"] == {
            "data_origin": "FIXTURE",
            "access_mode": "OFFLINE",
            "live_status": "NOT_LIVE",
        }
        assert rows["TASK10_APPROVED_LIVE"]["provenance"] == {
            "data_origin": "LIVE",
            "access_mode": "ONLINE",
            "live_status": "LIVE",
        }
        assert rows["TASK10_APPROVED_LIVE"]["warnings"] == []
        assert rows["TASK10_UNVERIFIED_LIVE"]["provenance"] == {
            "data_origin": "UNKNOWN",
            "access_mode": "UNKNOWN",
            "live_status": "UNKNOWN",
        }
        assert rows["TASK10_UNVERIFIED_LIVE"]["warnings"] == ["PROVIDER_LIVE_STATUS_UNVERIFIED"]
        assert "PROVIDER_CATALOG_CONTAINS_UNVERIFIED_LIVE_STATUS" in payload["warnings"]
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "DELETE FROM data_providers "
                    "WHERE code IN ('TASK10_APPROVED_LIVE', 'TASK10_UNVERIFIED_LIVE')"
                )
            )
        engine.dispose()


@pytest.mark.parametrize(
    ("security_id", "symbol", "expected_close"),
    [
        (MICRON_SECURITY_ID, "MU", "130.750000000001"),
        (INDUSTRIAL_FII_SECURITY_ID, "601138", "21.880000000001"),
    ],
)
def test_latest_close_returns_persisted_fixture_samples(
    api_contract: tuple[TestClient, dict[str, UUID], object],
    security_id: UUID,
    symbol: str,
    expected_close: str,
) -> None:
    client, _ids, _empty = api_contract
    response = client.get(
        f"/api/v1/securities/{security_id}/prices/latest",
        params=_scope(),
        headers={"X-Request-ID": f"latest-{symbol}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["provider_symbol"] == symbol
    assert payload["data"][0]["close"] == expected_close
    assert payload["source_record_ids"] == [payload["data"][0]["id"]]
    assert payload["provider_ids"] == [payload["data"][0]["provider_id"]]
    assert payload["provenance"] == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }
    assert response.headers["X-Request-ID"] == f"latest-{symbol}"


def test_history_range_is_inclusive_bounded_and_decimal_safe(
    api_contract: tuple[TestClient, dict[str, UUID], object],
) -> None:
    client, _ids, _empty = api_contract
    response = client.get(
        f"/api/v1/securities/{MICRON_SECURITY_ID}/prices",
        params={
            **_scope(),
            "date_from": "2026-07-09",
            "date_to": "2026-07-10",
            "limit": "100",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert [row["trading_date"] for row in payload["data"]] == ["2026-07-10", "2026-07-09"]
    assert all(isinstance(row["close"], str) for row in payload["data"])
    assert len(payload["data"]) <= 100


def test_actions_facts_and_documents_are_safe_raw_evidence_only(
    api_contract: tuple[TestClient, dict[str, UUID], object],
) -> None:
    client, _ids, _empty = api_contract
    paths = (
        "corporate-actions",
        "financial-facts",
        "documents",
    )
    payloads = []
    for path in paths:
        response = client.get(
            f"/api/v1/securities/{MICRON_SECURITY_ID}/{path}",
            params={**_scope(), "limit": "10"},
        )
        assert response.status_code == 200
        assert response.json()["data"]
        payloads.append(response.text.lower())
    assert '"cash_amount":"0.125000000001"' in payloads[0]
    assert '"value":"8123000000.123456789012"' in payloads[1]
    assert '"title":"micron quarterly filing metadata"' in payloads[2]
    forbidden = (
        "raw_payload",
        "inline_json",
        "storage_uri",
        "blob://",
        "confidence",
        "valuation",
        "margin",
        "growth",
        "ttm",
        "download",
        "content_body",
    )
    assert not any(value in text for text in payloads for value in forbidden)


def test_snapshot_scope_returns_exact_ids_without_newer_leakage(
    api_contract: tuple[TestClient, dict[str, UUID], object],
) -> None:
    client, ids, _empty = api_contract
    response = client.get(
        f"/api/v1/securities/{MICRON_SECURITY_ID}/prices",
        params={"snapshot_id": str(ids["mu_snapshot"]), "limit": "100"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot_id"] == str(ids["mu_snapshot"])
    assert payload["source_record_ids"] == [str(ids["mu_old"])]
    assert str(ids["mu_new"]) not in response.text
    assert payload["status"] == "PARTIAL"
    assert "SNAPSHOT_PARTIAL" in payload["warnings"]


def test_absent_financial_facts_are_partial_with_zero_fake_data(
    api_contract: tuple[TestClient, dict[str, UUID], object],
) -> None:
    client, ids, _empty = api_contract
    response = client.get(
        f"/api/v1/securities/{INDUSTRIAL_FII_SECURITY_ID}/financial-facts",
        params={"snapshot_id": str(ids["fii_snapshot"]), "limit": "100"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PARTIAL"
    assert payload["data"] == []
    assert payload["quality"]["record_count"] == 0
    assert "SNAPSHOT_CATEGORY_ABSENT:FINANCIAL_FACTS" in payload["warnings"]
    assert payload["provenance"] == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }


def test_snapshot_detail_and_items_preserve_partial_and_public_bound(
    api_contract: tuple[TestClient, dict[str, UUID], object],
) -> None:
    client, ids, _empty = api_contract
    detail = client.get(f"/api/v1/snapshots/{ids['mu_snapshot']}")
    items = client.get(
        f"/api/v1/snapshots/{ids['mu_snapshot']}/items",
        params={"limit": "100"},
    )
    assert detail.status_code == items.status_code == 200
    assert detail.json()["status"] == items.json()["status"] == "PARTIAL"
    assert detail.json()["data"][0]["status"] == "PARTIAL"
    assert len(items.json()["data"]) == 4
    assert set(items.json()["data"][0]) == {
        "id",
        "snapshot_id",
        "provider_id",
        "category",
        "source_record_type",
        "source_record_id",
        "source_published_at",
        "retrieved_at",
        "checksum",
        "created_at",
    }
    assert "checksum_input" not in items.text


@pytest.mark.parametrize(
    ("path", "params"),
    [
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/prices/latest",
            {},
        ),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/prices/latest",
            {"snapshot_id": str(MISSING_ID), **_scope()},
        ),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/prices",
            {**_scope(), "limit": "0"},
        ),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/prices",
            {**_scope(), "limit": "101"},
        ),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/prices",
            {**_scope(), "date_from": "2026-07-11", "date_to": "2026-07-10"},
        ),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/prices",
            {**_scope(), "date_from": "2025-07-09", "date_to": "2026-07-10"},
        ),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/prices",
            {"research_as_of_time": "2026-07-10T20:00:00", "limit": "10"},
        ),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/prices",
            {**_scope(), "sort": "trading_date desc"},
        ),
        (
            f"/api/v1/snapshots/{MISSING_ID}/items",
            {"limit": "0"},
        ),
    ],
)
def test_invalid_controls_use_uniform_safe_422(
    api_contract: tuple[TestClient, dict[str, UUID], object],
    path: str,
    params: dict[str, str],
) -> None:
    client, _ids, _empty = api_contract
    response = client.get(path, params=params)
    _assert_safe_error(response, 422, "REQUEST_VALIDATION_ERROR")
    assert "UUID" not in response.text


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/snapshots/{MISSING_ID}",
        f"/api/v1/snapshots/{MISSING_ID}/items",
        f"/api/v1/securities/{MICRON_SECURITY_ID}/prices?&snapshot_id={MISSING_ID}",
    ],
)
def test_missing_snapshot_ids_are_safe_404(
    api_contract: tuple[TestClient, dict[str, UUID], object],
    path: str,
) -> None:
    client, _ids, _empty = api_contract
    response = client.get(path)
    _assert_safe_error(response, 404, "SNAPSHOT_NOT_FOUND")


@pytest.mark.parametrize(
    "path",
    (
        "/api/v1/data/providers",
        f"/api/v1/snapshots/{MISSING_ID}",
    ),
)
def test_database_not_configured_is_safe_503(path: str) -> None:
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=None,
        api_prefix="/api/v1",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.get(path)
    _assert_safe_error(response, 503, "DATABASE_UNAVAILABLE")


@pytest.mark.parametrize(
    "path",
    (
        "/api/v1/data/providers",
        f"/api/v1/snapshots/{MISSING_ID}",
    ),
)
def test_configured_unreachable_database_is_safe_503_without_details(
    path: str,
) -> None:
    secret = "TASK10_DATABASE_SECRET"
    settings = Settings(
        _env_file=None,
        app_env=AppEnvironment.TEST,
        database_url=(
            "postgresql+psycopg://blocked_user:"
            f"{secret}@127.0.0.1:1/unreachable_task10_test?connect_timeout=1"
        ),
        api_prefix="/api/v1",
    )
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        with TestClient(create_app(settings), raise_server_exceptions=False) as client:
            response = client.get(path)
    _assert_safe_error(response, 503, "DATABASE_UNAVAILABLE")
    combined = f"{response.text}\n{stdout.getvalue()}\n{stderr.getvalue()}"
    assert secret not in combined
    assert "127.0.0.1:1" not in combined
    assert "connection refused" not in combined.lower()


def test_repository_failure_is_safe_503_without_details(
    api_contract: tuple[TestClient, dict[str, UUID], object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ids, _empty = api_contract
    sentinel = "SELECT secret FROM raw_payloads password=sentinel C:\\private\\payload.json"

    def fail_read(
        _repository: SqlAlchemyDataAccessRepository,
        _limit: int,
    ) -> tuple[object, ...]:
        raise RuntimeError(sentinel)

    monkeypatch.setattr(SqlAlchemyDataAccessRepository, "list_providers", fail_read)
    response = client.get("/api/v1/data/providers")
    _assert_safe_error(response, 503, "DATA_ACCESS_QUERY_FAILED")
    assert sentinel not in response.text and "sentinel" not in response.text


def test_openapi_has_exact_eight_gets_and_no_new_write_or_unsafe_controls(
    api_contract: tuple[TestClient, dict[str, UUID], object],
) -> None:
    client, _ids, _empty = api_contract
    document = client.get("/openapi.json").json()
    expected = {
        "/api/v1/data/providers",
        "/api/v1/securities/{security_id}/prices/latest",
        "/api/v1/securities/{security_id}/prices",
        "/api/v1/securities/{security_id}/corporate-actions",
        "/api/v1/securities/{security_id}/financial-facts",
        "/api/v1/securities/{security_id}/documents",
        "/api/v1/snapshots/{snapshot_id}",
        "/api/v1/snapshots/{snapshot_id}/items",
    }
    assert expected <= set(document["paths"])
    for path in expected:
        assert set(document["paths"][path]) == {"get"}
    rendered = str({path: document["paths"][path] for path in expected}).lower()
    for forbidden in (
        "raw_payload",
        "inline_json",
        "storage_uri",
        "refresh",
        "download",
        "provider_command",
        "sort",
        "sql",
    ):
        assert forbidden not in rendered


def test_get_does_not_commit_and_request_session_closes(
    api_contract: tuple[TestClient, dict[str, UUID], object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ids, _empty = api_contract
    original_close = Session.close
    commit_calls = 0
    close_calls = 0

    def record_commit(_session: Session) -> None:
        nonlocal commit_calls
        commit_calls += 1

    def record_close(session: Session) -> None:
        nonlocal close_calls
        close_calls += 1
        original_close(session)

    monkeypatch.setattr(Session, "commit", record_commit)
    monkeypatch.setattr(Session, "close", record_close)
    response = client.get("/api/v1/data/providers")
    assert response.status_code == 200
    assert commit_calls == 0
    assert close_calls == 1


def test_get_routes_never_fetch_ingest_build_or_read_blob(
    api_contract: tuple[TestClient, dict[str, UUID], object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, ids, _empty = api_contract

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("forbidden resource or mutation path was called")

    for owner, name in (
        (IngestionService, "ingest"),
        (SnapshotBuilder, "build"),
        (Stage1SseFixtureProvider, "fetch"),
        (Stage1NasdaqFixtureProvider, "fetch"),
        (Stage1SecFixtureProvider, "fetch"),
        (SafeHttpClient, "get"),
        (InMemoryBlobStorage, "get"),
        (LocalBlobStorage, "get"),
    ):
        monkeypatch.setattr(owner, name, forbidden)

    requests = (
        ("/api/v1/data/providers", {}),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/prices/latest",
            _scope(),
        ),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/prices",
            _scope(),
        ),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/corporate-actions",
            _scope(),
        ),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/financial-facts",
            _scope(),
        ),
        (
            f"/api/v1/securities/{MICRON_SECURITY_ID}/documents",
            _scope(),
        ),
        (f"/api/v1/snapshots/{ids['mu_snapshot']}", {}),
        (f"/api/v1/snapshots/{ids['mu_snapshot']}/items", {}),
    )
    for path, params in requests:
        assert client.get(path, params=params).status_code == 200
