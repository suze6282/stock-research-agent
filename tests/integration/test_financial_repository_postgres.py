from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from stock_research_agent.db.models.data_access import (
    DataProvider,
    DataSnapshot,
    IngestionRun,
    ProviderFinancialFact,
    ProviderRequestLog,
    RawPayload,
    SnapshotItem,
)
from stock_research_agent.db.models.financials import (
    CalculationRun,
    CanonicalFinancialConcept,
    DerivedMetric,
    NormalizedFinancialFact,
    ProviderFactMapping,
)
from stock_research_agent.db.repositories.financials import SqlAlchemyFinancialRepository
from stock_research_agent.db.repositories.security_master import (
    SqlAlchemySecurityMasterRepository,
)
from stock_research_agent.domain.financials.calculation_service import (
    MetricCalculationService,
)
from stock_research_agent.domain.financials.concepts import CANONICAL_CONCEPTS
from stock_research_agent.domain.financials.formulas import FORMULA_REGISTRY
from stock_research_agent.domain.financials.normalization import (
    FinancialNormalizationService,
)
from stock_research_agent.domain.financials.queries import FinancialQueryService
from stock_research_agent.domain.financials.seed import FinancialReferenceSeedService
from stock_research_agent.domain.securities.seed import (
    INDUSTRIAL_FII_SECURITY_ID,
    SecurityMasterSeedService,
)
from stock_research_agent.tools.registry import create_financial_tool_registry
from stock_research_agent.tools.schemas import FinancialMetricsEnvelope

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _integration_was_selected() -> bool:
    arguments = [value.replace("\\", "/").lower() for value in sys.argv[1:]]
    return any("tests/integration" in value for value in arguments) or "integration" in arguments


if TEST_DATABASE_URL is None and _integration_was_selected():
    raise pytest.UsageError("TEST_DATABASE_URL is required for financial repository tests")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


@pytest.fixture(scope="module")
def financial_engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    command.upgrade(Config("alembic.ini"), "head")
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE TABLE normalized_fact_inputs, calculation_inputs, "
                    "derived_metrics, calculation_runs, normalized_financial_facts, "
                    "financial_periods, provider_fact_mappings, formula_definitions, "
                    "canonical_financial_concepts CASCADE"
                )
            )
        engine.dispose()
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


@pytest.fixture
def clean_financial_tables(financial_engine: Engine) -> Iterator[sessionmaker[Session]]:
    with financial_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE normalized_fact_inputs, calculation_inputs, derived_metrics, "
                "calculation_runs, normalized_financial_facts, financial_periods, "
                "provider_fact_mappings, formula_definitions, canonical_financial_concepts CASCADE"
            )
        )
    factory = sessionmaker(financial_engine, expire_on_commit=False)
    yield factory


def test_reference_seed_is_transactional_and_idempotent(
    clean_financial_tables: sessionmaker[Session],
    financial_engine: Engine,
) -> None:
    service = FinancialReferenceSeedService()
    with clean_financial_tables.begin() as session:
        first = service.seed(SqlAlchemyFinancialRepository(session))
    with clean_financial_tables.begin() as session:
        second = service.seed(SqlAlchemyFinancialRepository(session))

    expected = len(CANONICAL_CONCEPTS) + len(FORMULA_REGISTRY)
    assert (first.inserted_count, first.existing_count) == (expected, 0)
    assert (second.inserted_count, second.existing_count) == (0, expected)
    with financial_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM canonical_financial_concepts")) == len(
            CANONICAL_CONCEPTS
        )
        assert connection.scalar(text("SELECT count(*) FROM formula_definitions")) == len(
            FORMULA_REGISTRY
        )
        assert connection.scalar(text("SELECT count(*) FROM provider_fact_mappings")) == 0


def test_empty_sample_snapshot_calculation_is_blocked_idempotent_and_null(
    clean_financial_tables: sessionmaker[Session],
) -> None:
    snapshot_id = UUID("90000000-0000-0000-0000-000000005001")
    with clean_financial_tables.begin() as session:
        SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
        FinancialReferenceSeedService().seed(SqlAlchemyFinancialRepository(session))
        snapshot = DataSnapshot(
            id=snapshot_id,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            research_as_of_time=datetime(2035, 1, 1, tzinfo=UTC),
            snapshot_version=501,
            status="BUILDING",
            completed_at=None,
            checksum=None,
            formula_version="raw-data-v1",
            notes="Stage 5 synthetic empty calculation test snapshot",
        )
        session.add(snapshot)
        session.flush()
        snapshot.status = "PARTIAL"
        snapshot.completed_at = datetime(2035, 1, 1, 0, 1, tzinfo=UTC)
        snapshot.checksum = "5" * 64
        session.flush()
        repository = SqlAlchemyFinancialRepository(session)

        first = MetricCalculationService().calculate_snapshot(snapshot_id, repository)
        replay = MetricCalculationService().calculate_snapshot(snapshot_id, repository)

        assert first == replay
        assert first.status.value == "BLOCKED"
        assert session.scalar(select(func.count()).select_from(CalculationRun)) == 1
        metrics = tuple(session.scalars(select(DerivedMetric)).all())
        assert len(metrics) == len(FORMULA_REGISTRY)
        assert all(metric.value is None and metric.value_state == "NULL" for metric in metrics)
        assert all(metric.quality_status == "BLOCKED" for metric in metrics)
        query_service = FinancialQueryService(repository)
        queried = query_service.metrics(
            INDUSTRIAL_FII_SECURITY_ID,
            snapshot_id,
            None,
            100,
        )
        assert len(queried.records) == len(FORMULA_REGISTRY)
        envelope = create_financial_tool_registry(query_service).execute(
            "get_financial_metrics",
            "1.0.0",
            {
                "security_id": INDUSTRIAL_FII_SECURITY_ID,
                "snapshot_id": snapshot_id,
                "limit": 100,
            },
        )
        assert isinstance(envelope, FinancialMetricsEnvelope)
        assert envelope.status == "BLOCKED"
        assert envelope.calculation_run_id == first.calculation_run_id


def test_concurrent_calculation_reuses_one_terminal_run(
    clean_financial_tables: sessionmaker[Session],
) -> None:
    snapshot_id = UUID("90000000-0000-0000-0000-000000005002")
    with clean_financial_tables.begin() as session:
        SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
        FinancialReferenceSeedService().seed(SqlAlchemyFinancialRepository(session))
        snapshot = DataSnapshot(
            id=snapshot_id,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            research_as_of_time=datetime(2035, 2, 1, tzinfo=UTC),
            snapshot_version=502,
            status="BUILDING",
            completed_at=None,
            checksum=None,
            formula_version="raw-data-v1",
            notes="Stage 5 concurrent calculation test snapshot",
        )
        session.add(snapshot)
        session.flush()
        snapshot.status = "PARTIAL"
        snapshot.completed_at = datetime(2035, 2, 1, 0, 1, tzinfo=UTC)
        snapshot.checksum = "9" * 64

    barrier = Barrier(2)

    def calculate() -> UUID:
        with clean_financial_tables.begin() as session:
            barrier.wait()
            result = MetricCalculationService().calculate_snapshot(
                snapshot_id,
                SqlAlchemyFinancialRepository(session),
            )
            return result.calculation_run_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        run_ids = tuple(executor.map(lambda _index: calculate(), range(2)))

    assert run_ids[0] == run_ids[1]
    with clean_financial_tables() as session:
        assert session.scalar(select(func.count()).select_from(CalculationRun)) == 1
        assert session.scalar(select(func.count()).select_from(DerivedMetric)) == len(
            FORMULA_REGISTRY
        )


def test_synthetic_exact_mappings_normalize_and_calculate_in_postgresql(
    clean_financial_tables: sessionmaker[Session],
) -> None:
    now = datetime(2036, 2, 1, tzinfo=UTC)
    as_of = datetime(2036, 3, 1, tzinfo=UTC)
    with clean_financial_tables.begin() as session:
        SecurityMasterSeedService().seed(SqlAlchemySecurityMasterRepository(session))
        FinancialReferenceSeedService().seed(SqlAlchemyFinancialRepository(session))
        provider = DataProvider(
            id=uuid4(),
            code="SYNTHETIC_FINANCIAL_TEST",
            name="Synthetic financial integration test",
            provider_type="FIXTURE",
            status="APPROVED",
            base_url=None,
            documentation_url=None,
            terms_status="VERIFIED",
            capabilities=["FINANCIAL_FACTS"],
        )
        session.add(provider)
        run = IngestionRun(
            id=uuid4(),
            provider_id=provider.id,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            category="FINANCIAL_FACTS",
            status="PASS",
            research_as_of_time=as_of,
            idempotency_key=f"stage5:synthetic:{uuid4().hex}",
            requested_at=now,
            started_at=now,
            completed_at=now,
            request_count=1,
            records_received=3,
            records_stored=3,
            warning_count=0,
            error_code=None,
            safe_error_message=None,
        )
        session.add(run)
        request_log = ProviderRequestLog(
            id=uuid4(),
            ingestion_run_id=run.id,
            provider_id=provider.id,
            caller_request_id=uuid4(),
            provider_request_id="synthetic-financial-test",
            endpoint_name="synthetic_fixture",
            method="GET",
            safe_url="https://example.invalid/synthetic-financial-test",
            request_started_at=now,
            response_received_at=now,
            http_status=200,
            attempt=1,
            cache_status="NOT_APPLICABLE",
            etag=None,
            last_modified=None,
            response_size=2,
            error_code=None,
        )
        session.add(request_log)
        payload = RawPayload(
            id=uuid4(),
            ingestion_run_id=run.id,
            provider_request_log_id=request_log.id,
            provider_id=provider.id,
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            category="FINANCIAL_FACTS",
            content_type="application/json",
            storage_uri=None,
            inline_json={},
            checksum_algorithm="sha256",
            checksum="6" * 64,
            source_published_at=now,
            retrieved_at=now,
            provider_version="1.0.0",
            parser_version="1.0.0",
            schema_version="1.0.0",
            byte_size=2,
        )
        session.add(payload)
        session.flush()
        fact_specs = (
            ("Revenue", "REVENUE", Decimal("100")),
            ("CostOfRevenue", "COST_OF_REVENUE", Decimal("60")),
            ("OperatingIncome", "OPERATING_INCOME", Decimal("15")),
        )
        facts: list[ProviderFinancialFact] = []
        for provider_concept, canonical_code, value in fact_specs:
            concept = session.scalar(
                select(CanonicalFinancialConcept).where(
                    CanonicalFinancialConcept.code == canonical_code
                )
            )
            assert concept is not None
            fact = ProviderFinancialFact(
                id=uuid4(),
                security_id=INDUSTRIAL_FII_SECURITY_ID,
                provider_id=provider.id,
                source_payload_id=payload.id,
                document_id=None,
                statement_type="INCOME_STATEMENT",
                provider_concept=provider_concept,
                reported_label=provider_concept,
                taxonomy="SYNTHETIC_GAAP",
                context_id="CONSOLIDATED",
                dimensions={},
                value=value,
                unit="ONE",
                currency_code="CNY",
                fiscal_year=2035,
                fiscal_quarter=None,
                fiscal_period="FY",
                period_start=date(2035, 1, 1),
                period_end=date(2035, 12, 31),
                instant_date=None,
                filed_at=now,
                source_published_at=now,
                form_type="ANNUAL_REPORT",
                is_annual=True,
                is_cumulative=False,
                is_audited=True,
                is_restated=False,
                provider_record_id=provider_concept,
                retrieved_at=now,
            )
            session.add(fact)
            facts.append(fact)
            session.add(
                ProviderFactMapping(
                    id=uuid4(),
                    provider_id=provider.id,
                    provider_concept=provider_concept,
                    taxonomy="SYNTHETIC_GAAP",
                    reported_label_pattern=None,
                    statement_type="INCOME_STATEMENT",
                    form_type="ANNUAL_REPORT",
                    context_rules=["CONSOLIDATED"],
                    dimension_rules=[],
                    canonical_concept_id=concept.id,
                    mapping_status="APPROVED",
                    mapping_version="1.0.0",
                    valid_from=None,
                    valid_to=None,
                    source_reference="Synthetic integration-test mapping only",
                    reviewed_by="Stage 5 integration test",
                )
            )
        snapshot = DataSnapshot(
            id=uuid4(),
            security_id=INDUSTRIAL_FII_SECURITY_ID,
            research_as_of_time=as_of,
            snapshot_version=1,
            status="BUILDING",
            completed_at=None,
            checksum=None,
            formula_version="raw-data-v1",
            notes="Stage 5 synthetic numeric integration test",
        )
        session.add(snapshot)
        session.flush()
        for fact in facts:
            session.add(
                SnapshotItem(
                    id=uuid4(),
                    snapshot_id=snapshot.id,
                    provider_id=provider.id,
                    category="FINANCIAL_FACTS",
                    source_record_type="provider_financial_facts",
                    source_record_id=fact.id,
                    source_published_at=now,
                    retrieved_at=now,
                    checksum_input=str(fact.id),
                    checksum="7" * 64,
                )
            )
        session.flush()
        snapshot.status = "COMPLETE"
        snapshot.completed_at = as_of
        snapshot.checksum = "8" * 64
        session.flush()
        repository = SqlAlchemyFinancialRepository(session)

        normalization = FinancialNormalizationService().normalize_snapshot(snapshot.id, repository)
        calculation = MetricCalculationService().calculate_snapshot(snapshot.id, repository)

        assert normalization.status.value == "PASS"
        assert normalization.normalized_fact_count == 3
        assert session.scalar(select(func.count()).select_from(NormalizedFinancialFact)) == 3
        assert calculation.status.value == "PARTIAL"
        metrics = {
            metric.metric_code: metric for metric in session.scalars(select(DerivedMetric)).all()
        }
        assert metrics["gross_margin"].value == Decimal("0.400000000000000000")
        assert metrics["operating_margin"].value == Decimal("0.150000000000000000")
        assert [fact.value for fact in facts] == [
            Decimal("100"),
            Decimal("60"),
            Decimal("15"),
        ]
