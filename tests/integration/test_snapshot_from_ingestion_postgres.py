from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session

from stock_research_agent.config import AppEnvironment, Settings
from stock_research_agent.db.models import RawPayload
from stock_research_agent.db.repositories.data_access import SqlAlchemyDataAccessRepository
from stock_research_agent.domain.data_access.enums import (
    DataCategory,
)
from stock_research_agent.domain.data_access.schemas import (
    DailyPriceBarWrite,
    DataProviderWrite,
    IngestionRunUpdate,
    IngestionRunWrite,
    ProviderInstrumentMappingWrite,
    ProviderRequestLogWrite,
    RawPayloadWrite,
)
from stock_research_agent.domain.data_access.snapshots import SnapshotBuilder, SnapshotBuildRequest
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.snapshot import (
    SnapshotFromIngestionPlan,
    SnapshotFromIngestionPlanRequest,
    SnapshotManifestReference,
    SnapshotPlanRegistry,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)
SECURITY_ID = UUID("91000000-0000-4000-8000-000000000001")
ISSUER_ID = UUID("92000000-0000-4000-8000-000000000001")


def _integration_was_explicitly_selected() -> bool:
    arguments = [argument.replace("\\", "/").lower() for argument in sys.argv[1:]]
    return any("tests/integration" in argument for argument in arguments)


if TEST_DATABASE_URL is None and _integration_was_explicitly_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for PostgreSQL integration tests")


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


class _Clock:
    def now(self) -> datetime:
        return NOW


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
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(config, "head")
    try:
        yield engine
    finally:
        engine.dispose()


def _seed_neutral_security(session: Session) -> None:
    parameters = {
        "market_id": UUID("93000000-0000-4000-8000-000000000001"),
        "exchange_id": UUID("94000000-0000-4000-8000-000000000001"),
        "issuer_id": ISSUER_ID,
        "security_id": SECURITY_ID,
    }
    session.execute(
        text(
            """
            INSERT INTO markets
                (id, code, name, country_code, default_currency_code, status)
            VALUES
                (:market_id, 'US_EQUITY', 'US Equity', 'US', 'USD', 'ACTIVE')
            """
        ),
        parameters,
    )
    session.execute(
        text(
            """
            INSERT INTO exchanges
                (id, market_id, mic, name, short_name, country_code, timezone,
                 default_currency_code, status)
            VALUES
                (:exchange_id, :market_id, 'XNAS', 'Nasdaq', 'Nasdaq', 'US',
                 'America/New_York', 'USD', 'ACTIVE')
            """
        ),
        parameters,
    )
    session.execute(
        text(
            """
            INSERT INTO issuers
                (id, legal_name, normalized_legal_name, display_name,
                 normalized_display_name, country_code, issuer_status)
            VALUES
                (:issuer_id, 'Synthetic Test Issuer', 'SYNTHETIC TEST ISSUER',
                 'Synthetic Test Issuer', 'SYNTHETIC TEST ISSUER', 'US', 'ACTIVE')
            """
        ),
        parameters,
    )
    session.execute(
        text(
            """
            INSERT INTO securities
                (id, issuer_id, exchange_id, symbol, normalized_symbol, display_name,
                 security_type, currency_code, listing_status, is_primary_listing)
            VALUES
                (:security_id, :issuer_id, :exchange_id, 'SYNTH10', 'SYNTH10',
                 'Synthetic Test Security', 'COMMON_STOCK', 'USD', 'ACTIVE', TRUE)
            """
        ),
        parameters,
    )


def _plan_registry() -> SnapshotPlanRegistry:
    return SnapshotPlanRegistry(
        registry_id="SNAPSHOT_PLAN_REGISTRY",
        registry_version="1.0.0",
        registry_checksum="f" * 64,
    )


def _ready_plan() -> SnapshotFromIngestionPlan:
    return _plan_registry().plan(
        SnapshotFromIngestionPlanRequest(
            security_id=SECURITY_ID,
            issuer_id=ISSUER_ID,
            research_as_of_time=NOW,
            manifests=(
                SnapshotManifestReference(
                    manifest_id=UUID("95000000-0000-4000-8000-000000000001"),
                    manifest_checksum="a" * 64,
                    approved=True,
                    license_allowed=True,
                ),
            ),
            document_version_ids=(),
            financial_fact_ids=(),
            mapping_version_ids=(),
            formula_version_ids=(),
            required_input_kinds=("DAILY_PRICE",),
            available_input_kinds=("DAILY_PRICE",),
            planner_version="1.0.0",
        )
    )


def _build_request() -> SnapshotBuildRequest:
    return SnapshotBuildRequest(
        security_id=SECURITY_ID,
        research_as_of_time=NOW,
        snapshot_version=1,
        categories=(DataCategory.DAILY_PRICES,),
        exchange_timezone="America/New_York",
    )


class _FailingBuilder:
    def build(self, request: SnapshotBuildRequest) -> object:
        del request
        raise RuntimeError("synthetic persistence failure")


def test_plan_checksum_and_persistence_fail_closed() -> None:
    registry = _plan_registry()
    plan = _ready_plan()
    tampered = plan.model_copy(update={"plan_checksum": "0" * 64})

    with pytest.raises(LiveEvidenceValidationError) as checksum_error:
        registry.create(
            tampered,
            build_request=_build_request(),
            builder=cast(SnapshotBuilder, _FailingBuilder()),
        )
    assert checksum_error.value.code == "SNAPSHOT_PLAN_CHECKSUM_MISMATCH"

    with pytest.raises(LiveEvidenceValidationError) as persistence_error:
        registry.create(
            plan,
            build_request=_build_request(),
            builder=cast(SnapshotBuilder, _FailingBuilder()),
        )
    assert persistence_error.value.code == "SNAPSHOT_PERSISTENCE_FAILED"


def test_ready_plan_creates_and_replays_snapshot_in_caller_transaction(
    snapshot_engine: Engine,
) -> None:
    with Session(snapshot_engine) as session:
        _seed_neutral_security(session)
        repository = SqlAlchemyDataAccessRepository(session)
        provider = repository.add_provider(
            DataProviderWrite(
                code="SYNTHETIC_GATE_A",
                name="Gate A synthetic test provider",
                provider_type="FIXTURE",
                status="APPROVED",
                terms_status="VERIFIED",
                capabilities=("DAILY_PRICES",),
            )
        )
        mapping = repository.add_provider_mapping(
            ProviderInstrumentMappingWrite(
                provider_id=provider.id,
                security_id=SECURITY_ID,
                provider_symbol="SYNTH10",
                provider_exchange_code="XNAS",
                valid_from=date(2026, 1, 1),
                is_primary=True,
                metadata={"marker": "SYNTHETIC_TEST_ONLY"},
                source_name="Gate A synthetic test",
            )
        )
        session.flush()
        run, created = repository.get_or_create_ingestion_run(
            IngestionRunWrite(
                provider_id=provider.id,
                security_id=SECURITY_ID,
                category=DataCategory.DAILY_PRICES,
                research_as_of_time=NOW,
                idempotency_key="gate-a:synthetic:snapshot",
                requested_at=NOW,
            )
        )
        assert created
        repository.update_ingestion_run(
            run.id,
            IngestionRunUpdate(status="RUNNING", started_at=NOW),
        )
        request_log = repository.add_request_log(
            ProviderRequestLogWrite(
                ingestion_run_id=run.id,
                provider_id=provider.id,
                caller_request_id=uuid4(),
                endpoint_name="SYNTHETIC_TEST_ONLY",
                method="GET",
                safe_url="https://fixtures.example.test/gate-a/synthetic.json",
                request_started_at=NOW,
                response_received_at=NOW,
                http_status=200,
                attempt=1,
                cache_status="MISS",
                response_size=33,
            )
        )
        raw_bytes = b'{"marker":"SYNTHETIC_TEST_ONLY"}\n'
        raw_payload = repository.add_raw_payload(
            RawPayloadWrite(
                ingestion_run_id=run.id,
                provider_request_log_id=request_log.id,
                provider_id=provider.id,
                security_id=SECURITY_ID,
                category=DataCategory.DAILY_PRICES,
                content_type="application/json",
                inline_json={"marker": "SYNTHETIC_TEST_ONLY"},
                checksum=hashlib.sha256(raw_bytes).hexdigest(),
                source_published_at=NOW,
                retrieved_at=NOW,
                provider_version="1.0.0",
                parser_version="1.0.0",
                schema_version="1.0.0",
                byte_size=len(raw_bytes),
            )
        )
        repository.add_daily_price_bar(
            DailyPriceBarWrite(
                security_id=SECURITY_ID,
                provider_id=provider.id,
                source_payload_id=raw_payload.id,
                provider_symbol="SYNTH10",
                trading_date=date(2026, 7, 13),
                open=Decimal("1"),
                high=Decimal("1"),
                low=Decimal("1"),
                close=Decimal("1"),
                volume=1,
                currency_code="USD",
                adjustment_type="UNADJUSTED",
                source_published_at=NOW,
                retrieved_at=NOW,
            )
        )
        repository.update_ingestion_run(
            run.id,
            IngestionRunUpdate(
                status="PASS",
                started_at=NOW,
                completed_at=NOW,
                request_count=1,
                records_received=1,
                records_stored=1,
            ),
        )
        assert session.scalars(select(RawPayload)).one().id == raw_payload.id

        plan_registry = _plan_registry()
        plan = plan_registry.plan(
            SnapshotFromIngestionPlanRequest(
                security_id=SECURITY_ID,
                issuer_id=ISSUER_ID,
                research_as_of_time=NOW,
                manifests=(
                    SnapshotManifestReference(
                        manifest_id=raw_payload.id,
                        manifest_checksum=raw_payload.checksum,
                        approved=True,
                        license_allowed=True,
                    ),
                ),
                document_version_ids=(),
                financial_fact_ids=(),
                mapping_version_ids=(mapping.id,),
                formula_version_ids=(),
                required_input_kinds=("DAILY_PRICE",),
                available_input_kinds=("DAILY_PRICE",),
                planner_version="1.0.0",
            )
        )
        build_request = SnapshotBuildRequest(
            security_id=SECURITY_ID,
            research_as_of_time=NOW,
            snapshot_version=1,
            categories=(DataCategory.DAILY_PRICES,),
            exchange_timezone="America/New_York",
        )
        builder = SnapshotBuilder(repository, clock=_Clock())

        first = plan_registry.create(plan, build_request=build_request, builder=builder)
        replay = plan_registry.create(plan, build_request=build_request, builder=builder)

        assert first.snapshot == replay.snapshot
        assert first.status == "COMPLETE"
        assert len(first.bindings) == 1
        assert first.bindings[0].binding_checksum == replay.bindings[0].binding_checksum
        assert session.in_transaction()
        session.commit()
