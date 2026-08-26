from __future__ import annotations

import ipaddress
import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from stock_research_agent import cli_live
from stock_research_agent.db.models import ProviderRequestAttempt
from stock_research_agent.db.models.live_evidence import (
    LiveAuthorizationEvent,
    LiveAuthorizationGrant,
    LiveExecutionApproval,
)
from stock_research_agent.db.repositories.live_evidence import (
    SqlAlchemyGateBAuditRepository,
    SqlAlchemySecAttemptReservationPort,
    SqlAlchemySecSettlementTransaction,
    SqlAlchemySecTerminalStore,
)
from stock_research_agent.db.repositories.providers import (
    SqlAlchemyProviderDefinitionRepository,
    SqlAlchemyProviderGovernanceRepository,
    SqlAlchemyProviderSyncRepository,
)
from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizedGateBExecution,
    GateBAuthorizationValidation,
)
from stock_research_agent.domain.live_evidence.gate_b_pilot import (
    SecArtifactSettlementService,
    SecDataQualityStopService,
    SecDocumentCitationResult,
)
from stock_research_agent.domain.providers.capabilities import ProviderCapabilityWrite
from stock_research_agent.domain.providers.credentials import CredentialReferenceRecord
from stock_research_agent.domain.providers.enums import (
    ProviderCapabilityStatus,
    ProviderDefinitionStatus,
    ProviderLicenseStatus,
    ProviderProductionStatus,
    ProviderSyncSliceStatus,
)
from stock_research_agent.domain.providers.licenses import (
    LicensePermission,
    SourceLicensePolicyWrite,
)
from stock_research_agent.domain.providers.policies import ProviderPolicyWrite
from stock_research_agent.domain.providers.quality import ProviderDataQualityValidator
from stock_research_agent.domain.providers.schemas import ProviderDefinitionWrite
from stock_research_agent.domain.providers.sync import (
    ProviderExecutionMode,
    ProviderSyncPlanRecord,
    ProviderSyncPlanWrite,
    ProviderSyncRequestWrite,
    ProviderSyncRunWrite,
)
from stock_research_agent.providers.cache import InMemoryResponseCache
from stock_research_agent.providers.credentials import EnvironmentCredentialResolver
from stock_research_agent.providers.http_client import SafeHttpClient
from stock_research_agent.providers.sec_edgar.policy import build_sec_http_client_policy
from stock_research_agent.providers.sec_edgar.retry import (
    SecAttemptKind,
    SecAttemptReservationRequest,
    SecGateBRetryController,
)
from stock_research_agent.providers.sec_edgar.transport import SecGateBTransportController
from tests.integration.test_gate_b_sec_pilot_postgres import _reservation_schema
from tests.integration.test_knowledge_repository_postgres import (
    _create_version,
    _seed_document_lineage,
)
from tests.unit.test_gate_b_corrective_orchestration_red import (
    _contact_reference,
    _context_for,
    _Documents,
    _exact_plan,
)
from tests.unit.test_sec_gate_b_pilot import _adapter, _Storage

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TEST_DATABASE_ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL")
NOW = datetime(2026, 8, 22, tzinfo=UTC)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        TEST_DATABASE_URL is None or TEST_DATABASE_ADMIN_URL is None,
        reason="loopback TEST_DATABASE_URL and TEST_DATABASE_ADMIN_URL are required",
    ),
]


@dataclass(frozen=True)
class _GateBScenario:
    sessions: sessionmaker[Session]
    execution: AuthorizedGateBExecution
    plan: ProviderSyncPlanRecord
    sync_run_id: UUID
    provider_definition_id: UUID
    provider_capability_id: UUID
    license_policy_id: UUID


def _alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


@pytest.fixture(scope="module")
def migrated_engine() -> Iterator[Engine]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_ADMIN_URL is not None
    base_url = make_url(TEST_DATABASE_URL)
    admin_url = make_url(TEST_DATABASE_ADMIN_URL)
    assert base_url.host in {"127.0.0.1", "localhost"}
    assert admin_url.host in {"127.0.0.1", "localhost"}
    assert base_url.port == admin_url.port == 55432
    assert base_url.database is not None and base_url.database.endswith("_test")
    assert admin_url.database == "postgres"

    database_name = f"stock_research_gate_b_3e_{uuid4().hex}_test"
    assert re.fullmatch(r"stock_research_gate_b_3e_[0-9a-f]{32}_test", database_name)
    database_url = base_url.set(database=database_name)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(
            text(f'CREATE DATABASE "{database_name}" OWNER stock_user TEMPLATE template0')
        )

    previous_app_env = os.environ.get("APP_ENV")
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = database_url.render_as_string(hide_password=False)
    try:
        command.upgrade(_alembic_config(), "head")
    finally:
        if previous_app_env is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = previous_app_env
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_database()")) == database_name
            assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 1
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin.dispose()


def _seed_gate_b_scenario(engine: Engine) -> _GateBScenario:
    sessions = sessionmaker(engine, expire_on_commit=False)
    exact = _exact_plan(include_artifact_kinds=True)
    version = f"1.0.{int(uuid4().hex[:4], 16)}"
    with sessions.begin() as session:
        definition = SqlAlchemyProviderDefinitionRepository(session).add_definition(
            ProviderDefinitionWrite(
                code="SEC_EDGAR_PUBLIC_V1",
                definition_version=version,
                adapter_version="1.0.0",
                display_name="SEC EDGAR Gate B Test",
                data_domain="REGULATORY_FILINGS",
                definition_status=ProviderDefinitionStatus.ACTIVE,
                production_status=ProviderProductionStatus.TEST_ONLY,
                official_domains=("data.sec.gov", "www.sec.gov"),
                policy_version=version,
                license_policy_version=version,
                credential_reference_id=None,
                source_register_version="1.0.0",
            )
        )
        governance = SqlAlchemyProviderGovernanceRepository(session)
        capability = governance.add_capability(
            ProviderCapabilityWrite(
                provider_definition_id=definition.id,
                code="SEC_FILING_DOCUMENT",
                capability_version=version,
                status=ProviderCapabilityStatus.IMPLEMENTED_OFFLINE,
                data_domain="REGULATORY_FILINGS",
                market_codes=("US_EQUITY",),
                security_types=("COMMON_STOCK",),
                operations=("READ_LIVE_VALIDATION",),
            )
        )
        policy = governance.add_policy(
            ProviderPolicyWrite(
                provider_definition_id=definition.id,
                policy_version=version,
                endpoint_policy_version="1.0.0",
                network_enabled=False,
                max_requests=3,
                max_response_bytes=20 * 1024 * 1024,
                max_total_bytes=26 * 1024 * 1024,
                max_duration_seconds=120,
                max_attempts=3,
                max_redirects=0,
                rate_limit_per_second=Decimal("1"),
                retry_base_delay_seconds=Decimal("1"),
                cache_enabled=False,
                cache_ttl_seconds=None,
                retention_days=30,
            )
        )
        license_policy = governance.add_license_policy(
            SourceLicensePolicyWrite(
                provider_definition_id=definition.id,
                policy_version=version,
                status=ProviderLicenseStatus.APPROVED,
                acquisition=LicensePermission.ALLOWED,
                raw_storage=LicensePermission.ALLOWED,
                cache=LicensePermission.PROHIBITED,
                derived_use=LicensePermission.ALLOWED,
                redistribution=LicensePermission.PROHIBITED,
                retention_days=30,
                deletion_required=False,
                attribution_required=True,
                terms_source_ids=("SEC_PUBLIC_ACCESS",),
                reviewed_at=NOW,
                expires_at=None,
            )
        )
        repository = SqlAlchemyProviderSyncRepository(session)
        token = uuid4().hex * 2
        request = repository.create_request(
            ProviderSyncRequestWrite(
                provider_definition_id=definition.id,
                provider_capability_id=capability.id,
                policy_id=policy.id,
                license_policy_id=license_policy.id,
                credential_reference_id=None,
                security_id=None,
                universe_code="GATE_B_MU",
                research_as_of_time=NOW,
                range_start=date(2025, 8, 28),
                range_end=date(2025, 8, 28),
                execution_mode=ProviderExecutionMode.LIVE_VALIDATION,
                scope={"cik": "0000723125", "symbol": "MU", "exchange": "XNAS"},
                budget={
                    "max_requests": 3,
                    "max_bytes": 26 * 1024 * 1024,
                    "max_attempts": 3,
                    "max_duration_seconds": 120,
                },
                request_checksum=token,
                idempotency_key=(uuid4().hex * 2),
            )
        )
        plan = repository.add_plan(
            ProviderSyncPlanWrite(
                sync_request_id=request.id,
                adapter_version="1.0.0",
                checkpoint_revision=None,
                slices=tuple(
                    json.loads(json.dumps(item, default=str))
                    for item in exact.slices  # type: ignore[attr-defined]
                ),
                plan_checksum=exact.plan_checksum,  # type: ignore[attr-defined]
            )
        )
        run = repository.create_run(
            ProviderSyncRunWrite(
                sync_request_id=request.id,
                sync_plan_id=plan.id,
                provider_definition_id=definition.id,
                provider_capability_id=capability.id,
            )
        )
        authorization_id = uuid4()
        approval_id = uuid4()
        security_id = uuid4()
        issuer_id = uuid4()
        reference_id = uuid4()
        authorization_checksum = uuid4().hex * 2
        execution = AuthorizedGateBExecution(
            authorization_id=authorization_id,
            authorization_checksum=authorization_checksum,
            approval_id=approval_id,
            plan_id=plan.id,
            plan_checksum=plan.plan_checksum,
            provider="SEC_EDGAR_PUBLIC_V1",
            security_id=security_id,
            issuer_id=issuer_id,
            provider_security_identifier="0000723125",
            credential_reference_id=reference_id,
            user_agent_reference_id=reference_id,
        )
        session.add(
            LiveAuthorizationGrant(
                id=authorization_id,
                status="ACTIVE",
                request_limit=4,
                byte_limit=26 * 1024 * 1024,
                canonical_checksum=authorization_checksum,
                scope={
                    "security_id": str(security_id),
                    "issuer_id": str(issuer_id),
                    "provider_security_identifier": "0000723125",
                },
                expires_at=NOW.replace(hour=1),
            )
        )
        session.flush()
        session.add_all(
            (
                LiveAuthorizationEvent(
                    id=uuid4(),
                    authorization_id=authorization_id,
                    sequence=1,
                    event_type="APPROVE",
                ),
                LiveAuthorizationEvent(
                    id=uuid4(),
                    authorization_id=authorization_id,
                    sequence=2,
                    event_type="ACTIVATE",
                ),
                LiveExecutionApproval(
                    id=approval_id,
                    authorization_id=authorization_id,
                    plan_id=plan.id,
                    plan_checksum=plan.plan_checksum,
                    approval_signature=uuid4().hex * 2,
                    state="VALID",
                    expires_at=NOW.replace(hour=1),
                ),
            )
        )
    bound_plan = exact.model_copy(  # type: ignore[attr-defined]
        update={
            "id": plan.id,
            "sync_request_id": plan.sync_request_id,
            "plan_checksum": plan.plan_checksum,
            "created_at": plan.created_at,
        }
    )
    return _GateBScenario(
        sessions=sessions,
        execution=execution,
        plan=bound_plan,
        sync_run_id=run.id,
        provider_definition_id=definition.id,
        provider_capability_id=capability.id,
        license_policy_id=license_policy.id,
    )


def _port(
    scenario: _GateBScenario,
    *,
    executable: bool = True,
) -> SqlAlchemySecAttemptReservationPort:
    context: AuthorizedGateBExecution | GateBAuthorizationValidation = scenario.execution
    if not executable:
        context = GateBAuthorizationValidation.model_validate(
            scenario.execution.model_dump(mode="python")
        )
    return SqlAlchemySecAttemptReservationPort(
        session_factory=scenario.sessions,
        execution=context,
        sync_run_id=scenario.sync_run_id,
        reserved_bytes=1024,
        clock=lambda: NOW,
    )


def _request(
    scenario: _GateBScenario,
    *,
    slice_id: str,
    endpoint_id: str,
    attempt_number: int,
    kind: SecAttemptKind = SecAttemptKind.INITIAL,
) -> SecAttemptReservationRequest:
    return SecAttemptReservationRequest(
        authorization_id=scenario.execution.authorization_id,
        plan_id=scenario.execution.plan_id,
        plan_checksum=scenario.execution.plan_checksum,
        slice_id=slice_id,
        endpoint_id=endpoint_id,
        attempt_number=attempt_number,
        kind=kind,
    )


def _insert_attempt(
    engine: Engine,
    run_id: UUID,
    *,
    attempt_number: int,
    slice_id: str,
) -> bool:
    try:
        with Session(engine) as session, session.begin():
            session.add(
                ProviderRequestAttempt(
                    id=uuid4(),
                    sync_run_id=run_id,
                    slice_id=slice_id,
                    attempt_number=attempt_number,
                    status=ProviderSyncSliceStatus.COMPLETED.value,
                    endpoint_id="SEC_FILING_DOCUMENT",
                    response_status_code=200,
                    response_bytes=128,
                    started_at=NOW,
                    completed_at=NOW,
                )
            )
        return True
    except IntegrityError:
        return False


def _seed_first_three_attempts(engine: Engine, scenario: _GateBScenario) -> None:
    assert _insert_attempt(
        engine,
        scenario.sync_run_id,
        attempt_number=1,
        slice_id="SEC_SUBMISSIONS",
    )
    assert _insert_attempt(
        engine,
        scenario.sync_run_id,
        attempt_number=2,
        slice_id="SEC_FILING_INDEX",
    )
    assert _insert_attempt(
        engine,
        scenario.sync_run_id,
        attempt_number=3,
        slice_id="SEC_FILING_INDEX",
    )


def test_red_062_migration_built_db_accepts_authoritative_gate_b_attempt_four(
    migrated_engine: Engine,
) -> None:
    scenario = _seed_gate_b_scenario(migrated_engine)
    _seed_first_three_attempts(migrated_engine, scenario)

    permit = _port(scenario).reserve(
        _request(
            scenario,
            slice_id="SEC_PRIMARY_DOCUMENT",
            endpoint_id="SEC_FILING_DOCUMENT",
            attempt_number=4,
        )
    )

    assert permit.attempt_number == 4
    with migrated_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM provider_request_attempts "
                    "WHERE sync_run_id=:run_id AND attempt_number=4"
                ),
                {"run_id": scenario.sync_run_id},
            )
            == 1
        )


def test_red_063_migration_built_db_rejects_attempt_five(migrated_engine: Engine) -> None:
    scenario = _seed_gate_b_scenario(migrated_engine)
    assert not _insert_attempt(
        migrated_engine,
        scenario.sync_run_id,
        attempt_number=5,
        slice_id="FORBIDDEN_ATTEMPT_FIVE",
    )


def test_red_065_non_executable_validation_cannot_persist_attempt_four(
    migrated_engine: Engine,
) -> None:
    scenario = _seed_gate_b_scenario(migrated_engine)
    with pytest.raises(ValueError, match="SEC_EXECUTION_START_REQUIRED"):
        _port(scenario, executable=False).reserve(
            _request(
                scenario,
                slice_id="SEC_PRIMARY_DOCUMENT",
                endpoint_id="SEC_FILING_DOCUMENT",
                attempt_number=4,
            )
        )


def test_red_065_authoritative_gate_b_context_persists_attempt_four(
    migrated_engine: Engine,
) -> None:
    scenario = _seed_gate_b_scenario(migrated_engine)
    _seed_first_three_attempts(migrated_engine, scenario)

    permit = _port(scenario).reserve(
        _request(
            scenario,
            slice_id="SEC_PRIMARY_DOCUMENT",
            endpoint_id="SEC_FILING_DOCUMENT",
            attempt_number=4,
        )
    )

    assert permit.attempt_number == 4


@pytest.mark.parametrize(
    ("slice_id", "endpoint_id"),
    (
        ("FORGED_GATE_B_SLICE", "SEC_FILING_DOCUMENT"),
        ("SEC_PRIMARY_DOCUMENT", "SEC_SUBMISSIONS_JSON"),
    ),
)
def test_red_065_gate_b_attempt_requires_persisted_plan_resource_binding(
    migrated_engine: Engine,
    slice_id: str,
    endpoint_id: str,
) -> None:
    scenario = _seed_gate_b_scenario(migrated_engine)

    with pytest.raises(ValueError, match="SEC_ATTEMPT_RESERVATION_REQUIRED"):
        _port(scenario).reserve(
            _request(
                scenario,
                slice_id=slice_id,
                endpoint_id=endpoint_id,
                attempt_number=1,
            )
        )

    with migrated_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM provider_request_attempts "
                    "WHERE sync_run_id = :sync_run_id"
                ),
                {"sync_run_id": scenario.sync_run_id},
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM live_authorization_consumptions "
                    "WHERE authorization_id = :authorization_id"
                ),
                {"authorization_id": scenario.execution.authorization_id},
            )
            == 0
        )


def test_red_065_repeated_slice_cannot_claim_initial_attempt_kind(
    migrated_engine: Engine,
) -> None:
    scenario = _seed_gate_b_scenario(migrated_engine)
    port = _port(scenario)
    port.reserve(
        _request(
            scenario,
            slice_id="SEC_SUBMISSIONS",
            endpoint_id="SEC_SUBMISSIONS_JSON",
            attempt_number=1,
        )
    )

    with pytest.raises(ValueError, match="SEC_ATTEMPT_RESERVATION_REQUIRED"):
        port.reserve(
            _request(
                scenario,
                slice_id="SEC_SUBMISSIONS",
                endpoint_id="SEC_SUBMISSIONS_JSON",
                attempt_number=2,
                kind=SecAttemptKind.INITIAL,
            )
        )

    with migrated_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM provider_request_attempts "
                    "WHERE sync_run_id = :sync_run_id"
                ),
                {"sync_run_id": scenario.sync_run_id},
            )
            == 1
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM live_authorization_consumptions "
                    "WHERE authorization_id = :authorization_id"
                ),
                {"authorization_id": scenario.execution.authorization_id},
            )
            == 1
        )


def _fixture_insert(engine: Engine, run_id: UUID, attempt_number: int) -> bool:
    return _insert_attempt(
        engine,
        run_id,
        attempt_number=attempt_number,
        slice_id=f"FIXTURE_ATTEMPT_{attempt_number}",
    )


def _attempt_constraint(engine: Engine) -> str:
    with engine.connect() as connection:
        definition = connection.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_provider_request_attempts_bounds'"
            )
        )
    assert isinstance(definition, str)
    return definition


def _assert_complete_attempt_constraint(definition: str) -> None:
    assert "response_bytes >= 0" in definition
    assert "response_status_code IS NULL" in definition
    assert "response_status_code >= 100" in definition
    assert "response_status_code <= 599" in definition


def test_red_066_fixture_matches_migration_built_attempt_constraint(
    migrated_engine: Engine,
) -> None:
    migrated = _seed_gate_b_scenario(migrated_engine)
    migration_results = tuple(
        _insert_attempt(
            migrated_engine,
            migrated.sync_run_id,
            attempt_number=attempt_number,
            slice_id=f"MIGRATION_ATTEMPT_{attempt_number}",
        )
        for attempt_number in (3, 4, 5)
    )
    with _reservation_schema() as (fixture_engine, _sessions, _execution, run_id):
        fixture_results = tuple(
            _fixture_insert(fixture_engine, run_id, attempt_number) for attempt_number in (3, 4, 5)
        )
        fixture_constraint = _attempt_constraint(fixture_engine)

    assert migration_results == fixture_results == (True, True, False)
    _assert_complete_attempt_constraint(_attempt_constraint(migrated_engine))
    _assert_complete_attempt_constraint(fixture_constraint)


class _RateLimiter:
    def acquire(self, bucket: str) -> None:
        del bucket


class _PersistedDocuments(_Documents):
    def __init__(self, document_version_id: UUID) -> None:
        self._document_version_id = document_version_id

    def admit(self, committed: object, validated: object) -> SecDocumentCitationResult:
        return (
            super()
            .admit(committed, validated)
            .model_copy(update={"document_version_id": self._document_version_id})
        )


def _transport(
    reservations: SqlAlchemySecAttemptReservationPort,
) -> tuple[SecGateBTransportController, list[str], list[str]]:
    sends: list[str] = []
    dns_calls: list[str] = []
    index_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal index_attempts
        path = request.url.path
        sends.append(path)
        if path.endswith("CIK0000723125.json"):
            body = json.dumps(
                {
                    "cik": "0000723125",
                    "filings": [
                        {
                            "accessionNumber": "0000723125-25-000028",
                            "form": "10-K",
                            "filingDate": "2025-10-03",
                            "reportDate": "2025-08-28",
                            "acceptanceDateTime": "2025-10-03T10:30:00Z",
                            "primaryDocument": "mu-20250828.htm",
                        }
                    ],
                },
                separators=(",", ":"),
            ).encode()
            return httpx.Response(
                200,
                content=body,
                headers={"content-type": "application/json"},
                request=request,
            )
        if path.endswith("index.json"):
            index_attempts += 1
            if index_attempts == 1:
                return httpx.Response(503, content=b"transient", request=request)
            return httpx.Response(
                200,
                content=b"<html>mu-20250828.htm offline filing index</html>",
                headers={"content-type": "text/html"},
                request=request,
            )
        return httpx.Response(
            200,
            content=b"<html>offline primary filing document</html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    def client_factory(identity: object) -> SafeHttpClient:
        def resolver(host: str) -> tuple[ipaddress.IPv4Address, ...]:
            dns_calls.append(host)
            return (ipaddress.ip_address("93.184.216.34"),)

        return SafeHttpClient(
            build_sec_http_client_policy(network_enabled=True),
            cache=InMemoryResponseCache(),
            rate_limiter=_RateLimiter(),
            request_identity=identity,  # type: ignore[arg-type]
            transport=httpx.MockTransport(handler),
            resolver=resolver,  # type: ignore[arg-type]
        )

    controller = SecGateBTransportController(
        credential_resolver=EnvironmentCredentialResolver(
            {"SEC_EDGAR_CONTACT_IDENTITY": "offline-contact"}
        ),
        reservations=reservations,
        retry_controller=SecGateBRetryController(),
        http_client_factory=client_factory,
        clock=lambda: NOW,
    )
    return controller, sends, dns_calls


def test_red_067_full_four_attempt_gate_b_succeeds_on_migration_built_db(
    migrated_engine: Engine,
) -> None:
    scenario = _seed_gate_b_scenario(migrated_engine)
    _logical_document_id, document_value = _seed_document_lineage(migrated_engine)
    document_version_id = _create_version(migrated_engine, document_value)
    execution_start = _port(scenario, executable=False)
    transport, sends, dns_calls = _transport(execution_start)
    terminal_store = SqlAlchemySecTerminalStore(
        session_factory=scenario.sessions,
        execution=scenario.execution,
        provider_definition_id=scenario.provider_definition_id,
        provider_capability_id=scenario.provider_capability_id,
        sync_run_id=scenario.sync_run_id,
        started_at=NOW,
        expires_at=NOW.replace(hour=1),
        max_requests=4,
        max_bytes=26 * 1024 * 1024,
        clock=lambda: NOW,
    )
    application = cli_live.authorized_sec_pilot_application_factory(
        execution_start=execution_start,
        audit_repository=SqlAlchemyGateBAuditRepository(
            session_factory=scenario.sessions,
            sync_run_id=scenario.sync_run_id,
        ),
        transport=transport,
        adapter=_adapter(),
        settlement=SecArtifactSettlementService(
            storage=_Storage(),
            transaction_factory=lambda: SqlAlchemySecSettlementTransaction(scenario.sessions),
        ),
        documents=_PersistedDocuments(document_version_id),
        data_quality=SecDataQualityStopService(
            validator=ProviderDataQualityValidator(),
            terminal_store=terminal_store,
        ),
        artifact_id_factory=uuid4,
        ingestion_context_factory=lambda resource: _context_for(resource).model_copy(
            update={
                "provider_definition_id": scenario.provider_definition_id,
                "provider_capability_id": scenario.provider_capability_id,
                "sync_run_id": scenario.sync_run_id,
                "license_policy_id": scenario.license_policy_id,
                "security_id": scenario.execution.security_id,
            }
        ),
    )
    contact_reference: CredentialReferenceRecord = _contact_reference().model_copy(
        update={
            "provider_definition_id": scenario.provider_definition_id,
            "id": scenario.execution.user_agent_reference_id,
        }
    )

    try:
        audit = application.execute_authorized(
            GateBAuthorizationValidation.model_validate(
                scenario.execution.model_dump(mode="python")
            ),
            plan=scenario.plan,
            contact_reference=contact_reference,
        )
    except IntegrityError as error:
        with migrated_engine.connect() as connection:
            attempt_sequence = tuple(
                connection.scalars(
                    text(
                        "SELECT attempt_number FROM provider_request_attempts "
                        "WHERE sync_run_id=:run_id ORDER BY attempt_number"
                    ),
                    {"run_id": scenario.sync_run_id},
                )
            )
        raise AssertionError(
            "ATTEMPT_FOUR_BLOCKED_BY_MIGRATED_SCHEMA "
            f"persisted={attempt_sequence!r} sends={len(sends)} retries=1"
        ) from error

    assert tuple(attempt.attempt_number for attempt in audit.attempts) == (1, 2, 3, 4)
    assert sum(attempt.attempt_kind == "RETRY" for attempt in audit.attempts) == 1
    assert tuple(resource.slice_id for resource in audit.resources) == (
        "SEC_SUBMISSIONS",
        "SEC_FILING_INDEX",
        "SEC_PRIMARY_DOCUMENT",
    )
    assert len(sends) == len(dns_calls) == 4
    assert audit.terminal_status == "PASSED"
