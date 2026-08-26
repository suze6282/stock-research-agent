from __future__ import annotations

import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker

from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizedGateBExecution,
)
from stock_research_agent.domain.providers.canonical import (
    canonical_provider_json,
    provider_checksum,
)
from stock_research_agent.providers.sec_edgar.retry import (
    SecAttemptKind,
    SecAttemptReservationRequest,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
NOW = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)
_RESERVATION_PLAN_SLICES = (
    {
        "slice_id": "SEC_SUBMISSIONS",
        "request_parameters": {"endpoint_id": "SEC_SUBMISSIONS_JSON"},
    },
    {
        "slice_id": "SEC_FILING_INDEX",
        "request_parameters": {"endpoint_id": "SEC_FILING_DOCUMENT"},
    },
    {
        "slice_id": "SEC_PRIMARY_DOCUMENT",
        "request_parameters": {"endpoint_id": "SEC_FILING_DOCUMENT"},
    },
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def _execution(authorization_id: UUID, plan_id: UUID) -> AuthorizedGateBExecution:
    return AuthorizedGateBExecution(
        authorization_id=authorization_id,
        authorization_checksum="a" * 64,
        approval_id=uuid4(),
        plan_id=plan_id,
        plan_checksum="b" * 64,
        provider="SEC_EDGAR_PUBLIC_V1",
        security_id=uuid4(),
        issuer_id=uuid4(),
        provider_security_identifier="0000723125",
        credential_reference_id=uuid4(),
        user_agent_reference_id=uuid4(),
    )


@contextmanager
def _reservation_schema() -> Iterator[tuple[Engine, object, AuthorizedGateBExecution, UUID]]:
    assert TEST_DATABASE_URL is not None
    assert TEST_DATABASE_URL.rsplit("/", maxsplit=1)[-1].endswith("_test")
    admin = create_engine(TEST_DATABASE_URL)
    schema = f"gate_b_reservation_{uuid4().hex}"
    authorization_id, plan_id, run_id = uuid4(), uuid4(), uuid4()
    execution = _execution(authorization_id, plan_id)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(
            text(
                f'''CREATE TABLE "{schema}".live_authorization_grants (
                    id uuid PRIMARY KEY, request_limit integer NOT NULL,
                    byte_limit integer NOT NULL, status varchar(16) NOT NULL,
                    canonical_checksum varchar(64) NOT NULL,
                    scope jsonb NOT NULL, expires_at timestamptz NOT NULL
                );
                CREATE TABLE "{schema}".live_authorization_consumptions (
                    id uuid PRIMARY KEY, authorization_id uuid NOT NULL,
                    request_attempt_id uuid NOT NULL, reserved_bytes integer NOT NULL,
                    actual_bytes integer, socket_opened boolean, state varchar(16) NOT NULL,
                    reserved_at timestamptz NOT NULL, settled_at timestamptz,
                    UNIQUE (authorization_id, request_attempt_id)
                );
                CREATE TABLE "{schema}".provider_sync_runs (
                    id uuid PRIMARY KEY, sync_plan_id uuid NOT NULL
                );
                CREATE TABLE "{schema}".provider_sync_plans (
                    id uuid PRIMARY KEY, plan_checksum varchar(64) NOT NULL,
                    slices jsonb NOT NULL
                );
                CREATE TABLE "{schema}".provider_definitions (
                    id uuid PRIMARY KEY, code varchar(64) NOT NULL
                );
                CREATE TABLE "{schema}".provider_request_attempts (
                    id uuid PRIMARY KEY, sync_run_id uuid NOT NULL, slice_id varchar(64) NOT NULL,
                    attempt_number integer NOT NULL, status varchar(16) NOT NULL,
                    endpoint_id varchar(128) NOT NULL, response_status_code integer,
                    response_bytes integer NOT NULL, started_at timestamptz NOT NULL,
                    completed_at timestamptz, safe_error_code varchar(128),
                    created_at timestamptz NOT NULL DEFAULT now(),
                    CONSTRAINT ck_provider_request_attempts_bounds CHECK (
                        attempt_number BETWEEN 1 AND 4 AND response_bytes >= 0
                        AND (response_status_code IS NULL
                             OR response_status_code BETWEEN 100 AND 599)
                    ),
                    UNIQUE (sync_run_id, slice_id, attempt_number)
                );
                CREATE TABLE "{schema}".provider_data_quality_issues (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), sync_run_id uuid NOT NULL,
                    manifest_id uuid NOT NULL, rule_code varchar(128) NOT NULL,
                    severity varchar(16) NOT NULL, status varchar(16) NOT NULL,
                    safe_detail varchar(1024) NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE "{schema}".provider_live_validation_runs (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    provider_definition_id uuid NOT NULL,
                    provider_capability_id uuid NOT NULL, authorization_id varchar(128) NOT NULL,
                    live_authorization_grant_id uuid, status varchar(32) NOT NULL,
                    max_requests integer NOT NULL, max_bytes integer NOT NULL,
                    consumed_requests integer NOT NULL, consumed_bytes integer NOT NULL,
                    expires_at timestamptz NOT NULL, started_at timestamptz,
                    completed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE "{schema}".provider_audit_events (
                    id uuid PRIMARY KEY, provider_definition_id uuid NOT NULL,
                    sync_run_id uuid, actor_type varchar(64) NOT NULL,
                    action_code varchar(128) NOT NULL, decision_code varchar(128) NOT NULL,
                    safe_summary varchar(1024) NOT NULL, event_checksum varchar(64) NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE "{schema}".provider_raw_artifacts (
                    id uuid PRIMARY KEY, provider_definition_id uuid NOT NULL,
                    sync_run_id uuid NOT NULL, request_attempt_id uuid NOT NULL,
                    source_checksum varchar(64) NOT NULL,
                    acquired_at timestamptz NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now()
                )'''
            )
        )
        connection.execute(
            text(
                f'INSERT INTO "{schema}".live_authorization_grants '
                "(id, request_limit, byte_limit, status, canonical_checksum, scope, expires_at) "
                "VALUES (:authorization_id, 4, 4096, 'ACTIVE', :checksum, "
                "CAST(:scope AS jsonb), :expires_at)"
            ),
            {
                "authorization_id": authorization_id,
                "checksum": execution.authorization_checksum,
                "scope": json.dumps(
                    {
                        "security_id": str(execution.security_id),
                        "issuer_id": str(execution.issuer_id),
                        "provider_security_identifier": execution.provider_security_identifier,
                    }
                ),
                "expires_at": NOW.replace(hour=1),
            },
        )
        connection.execute(
            text(
                f'INSERT INTO "{schema}".provider_sync_plans (id, plan_checksum, slices) '
                "VALUES (:plan_id, :checksum, CAST(:slices AS jsonb))"
            ),
            {
                "plan_id": plan_id,
                "checksum": "b" * 64,
                "slices": json.dumps(_RESERVATION_PLAN_SLICES),
            },
        )
        connection.execute(
            text(
                f'INSERT INTO "{schema}".provider_sync_runs (id, sync_plan_id) '
                "VALUES (:run_id, :plan_id)"
            ),
            {"run_id": run_id, "plan_id": plan_id},
        )
    scoped_url = f"{TEST_DATABASE_URL}?options=-csearch_path%3D{schema}"
    engine = create_engine(scoped_url)
    try:
        yield (
            engine,
            sessionmaker(engine, expire_on_commit=False),
            execution,
            run_id,
        )
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _request(
    execution: AuthorizedGateBExecution,
    slice_id: str,
    attempt: int,
    *,
    kind: SecAttemptKind = SecAttemptKind.INITIAL,
) -> SecAttemptReservationRequest:
    endpoint_id = "SEC_SUBMISSIONS_JSON" if slice_id == "SEC_SUBMISSIONS" else "SEC_FILING_DOCUMENT"
    return SecAttemptReservationRequest(
        authorization_id=execution.authorization_id,
        plan_id=execution.plan_id,
        plan_checksum=execution.plan_checksum,
        slice_id=slice_id,
        endpoint_id=endpoint_id,
        attempt_number=attempt,
        kind=kind,
    )


def test_red_045_postgres_initial_reservation_commits_before_transport() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        port = module.SqlAlchemySecAttemptReservationPort(
            session_factory=sessions,
            execution=execution,
            sync_run_id=run_id,
            reserved_bytes=1024,
            clock=lambda: NOW,
        )
        permit = port.reserve(_request(execution, "SEC_SUBMISSIONS", 1))
        with engine.connect() as connection:
            attempts = connection.scalar(text("SELECT count(*) FROM provider_request_attempts"))
            consumptions = connection.scalar(
                text("SELECT count(*) FROM live_authorization_consumptions")
            )
        assert attempts == consumptions == 1
        assert permit.request_attempt_id is not None


def test_red_036_postgres_concurrent_retry_reservation_allows_one_sender() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        initial = module.SqlAlchemySecAttemptReservationPort(
            session_factory=sessions,
            execution=execution,
            sync_run_id=run_id,
            reserved_bytes=1024,
            clock=lambda: NOW,
        )
        initial.reserve(_request(execution, "SEC_SUBMISSIONS", 1))
        barrier = Barrier(2)

        def reserve_retry(slice_id: str) -> str:
            port = module.SqlAlchemySecAttemptReservationPort(
                session_factory=sessions,
                execution=execution,
                sync_run_id=run_id,
                reserved_bytes=1024,
                clock=lambda: NOW,
            )
            barrier.wait(timeout=5)
            try:
                port.reserve(_request(execution, slice_id, 2, kind=SecAttemptKind.RETRY))
                return "RESERVED"
            except ValueError as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(reserve_retry, ("SEC_SUBMISSIONS", "SEC_SUBMISSIONS")))
        assert results.count("RESERVED") == 1
        assert any("SEC_RETRY_BUDGET_EXHAUSTED" in result for result in results)
        with engine.connect() as connection:
            retries = connection.scalar(
                text("SELECT count(*) FROM provider_request_attempts WHERE attempt_number > 1")
            )
        assert retries == 1


def test_postgres_fifth_actual_attempt_is_denied_before_transport() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (_engine, sessions, execution, run_id):
        port = module.SqlAlchemySecAttemptReservationPort(
            session_factory=sessions,
            execution=execution,
            sync_run_id=run_id,
            reserved_bytes=1024,
            clock=lambda: NOW,
        )
        requests = (
            _request(execution, "SEC_SUBMISSIONS", 1),
            _request(execution, "SEC_FILING_INDEX", 2),
            _request(execution, "SEC_FILING_INDEX", 3, kind=SecAttemptKind.RETRY),
            _request(execution, "SEC_PRIMARY_DOCUMENT", 4),
        )
        for request in requests:
            port.reserve(request)
        with pytest.raises(ValueError, match="SEC_ATTEMPT_BUDGET_EXHAUSTED"):
            port.reserve(_request(execution, "SEC_PRIMARY_DOCUMENT", 4))


def test_postgres_reservation_rolls_back_consumption_and_attempt_together() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO provider_request_attempts "
                    "(id, sync_run_id, slice_id, attempt_number, status, endpoint_id, "
                    "response_bytes, started_at) VALUES "
                    "(:id, :run_id, 'SEC_SUBMISSIONS', 1, 'PENDING', 'SEC_SUBMISSIONS', 0, :now)"
                ),
                {"id": uuid4(), "run_id": run_id, "now": NOW},
            )
        port = module.SqlAlchemySecAttemptReservationPort(
            session_factory=sessions,
            execution=execution,
            sync_run_id=run_id,
            reserved_bytes=1024,
            clock=lambda: NOW,
        )
        with pytest.raises(ValueError, match="PROVIDER_ATTEMPT_CONFLICT"):
            port.reserve(_request(execution, "SEC_SUBMISSIONS", 1))
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT count(*) FROM live_authorization_consumptions")) == 0
            )


def test_red_049_postgres_data_quality_stop_is_committed_and_auditable() -> None:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import LiveValidationResult
    from tests.integration.test_gate_b_corrective_postgres_red import (
        _install_complete_terminal_lineage,
    )

    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        primary_attempt_id, primary_artifact_id = _install_complete_terminal_lineage(engine, run_id)
        store = module.SqlAlchemySecTerminalStore(
            session_factory=sessions,
            execution=execution,
            provider_definition_id=uuid4(),
            provider_capability_id=uuid4(),
            sync_run_id=run_id,
            started_at=NOW,
            expires_at=datetime(2026, 8, 20, 1, tzinfo=UTC),
            max_requests=3,
            max_bytes=4096,
            clock=lambda: NOW,
        )
        result = LiveValidationResult(
            status="PASSED",
            artifact_id=primary_artifact_id,
            manifest_id=uuid4(),
            request_attempt_id=primary_attempt_id,
            document_version_id=uuid4(),
            citation_ids=(uuid4(),),
            data_quality_issue_count=0,
        )

        event_id = store.commit(result, ())

        with engine.connect() as connection:
            terminal = connection.execute(
                text("SELECT status FROM provider_live_validation_runs")
            ).scalar_one()
            event = connection.execute(
                text(
                    "SELECT action_code, decision_code, safe_summary "
                    "FROM provider_audit_events WHERE id = :id"
                ),
                {"id": event_id},
            ).one()
        assert terminal == "PASS"
        assert event.action_code == "DATA_QUALITY_STOP"
        assert event.decision_code == "PASSED"
        assert "DATA_QUALITY" in event.safe_summary


def test_red_059_resource_failure_terminal_is_committed_and_auditable() -> None:
    from stock_research_agent.domain.live_evidence.gate_b_pilot import LiveValidationResult

    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        port = module.SqlAlchemySecAttemptReservationPort(
            session_factory=sessions,
            execution=execution,
            sync_run_id=run_id,
            reserved_bytes=1024,
            clock=lambda: NOW,
        )
        permit = port.reserve(_request(execution, "SEC_SUBMISSIONS", 1))
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE provider_request_attempts SET status='ABANDONED', "
                    "safe_error_code='SEC_TIMEOUT_ABORT', completed_at=:now "
                    "WHERE id=:attempt_id"
                ),
                {"attempt_id": permit.request_attempt_id, "now": NOW},
            )
            connection.execute(
                text(
                    "UPDATE live_authorization_consumptions SET state='ABANDONED', "
                    "actual_bytes=0, socket_opened=false, settled_at=:now "
                    "WHERE request_attempt_id=:attempt_id"
                ),
                {"attempt_id": permit.request_attempt_id, "now": NOW},
            )
        store = module.SqlAlchemySecTerminalStore(
            session_factory=sessions,
            execution=execution,
            provider_definition_id=uuid4(),
            provider_capability_id=uuid4(),
            sync_run_id=run_id,
            started_at=NOW,
            expires_at=datetime(2026, 8, 20, 1, tzinfo=UTC),
            max_requests=3,
            max_bytes=4096,
            clock=lambda: NOW,
        )
        result = LiveValidationResult(
            status="BLOCKED",
            terminal_stage="RESOURCE_ORCHESTRATION",
            request_attempt_id=permit.request_attempt_id,
            data_quality_issue_count=0,
            stop_reason="SEC_TIMEOUT_ABORT",
            failed_ordinal=0,
            failed_slice_id="SEC_SUBMISSIONS",
        )

        store.commit(result, ())

        with sessions() as session:
            audit = module.get_gate_b_audit_view(session, run_id)
        assert audit is not None
        assert audit.terminal_status == "BLOCKED"
        assert audit.terminal_stage == "RESOURCE_ORCHESTRATION"
        assert audit.failed_ordinal == 0
        assert audit.failed_slice_id == "SEC_SUBMISSIONS"
        assert audit.stop_reason == "SEC_TIMEOUT_ABORT"
        assert len(audit.attempts) == 1
        assert audit.attempts[0].status == "ABANDONED"
        assert audit.attempts[0].safe_error_code == "SEC_TIMEOUT_ABORT"


def test_red_044_committed_audit_view_links_authorization_attempt_and_artifact() -> None:
    from sqlalchemy.orm import Session

    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        definition_id = uuid4()
        port = module.SqlAlchemySecAttemptReservationPort(
            session_factory=sessions,
            execution=execution,
            sync_run_id=run_id,
            reserved_bytes=1024,
            clock=lambda: NOW,
        )
        permit = port.reserve(_request(execution, "SEC_SUBMISSIONS", 1))
        artifact_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO provider_definitions (id, code) "
                    "VALUES (:id, 'SEC_EDGAR_PUBLIC_V1')"
                ),
                {"id": definition_id},
            )
            connection.execute(
                text(
                    "UPDATE live_authorization_consumptions SET state='SETTLED', "
                    "actual_bytes=128, socket_opened=true, settled_at=:now"
                ),
                {"now": NOW},
            )
            connection.execute(
                text(
                    "UPDATE provider_request_attempts SET status='COMPLETED', "
                    "response_bytes=128, completed_at=:now"
                ),
                {"now": NOW},
            )
            connection.execute(
                text(
                    "INSERT INTO provider_raw_artifacts "
                    "(id, provider_definition_id, sync_run_id, request_attempt_id, "
                    "source_checksum, acquired_at) VALUES "
                    "(:id, :definition_id, :run_id, :attempt_id, :checksum, :now)"
                ),
                {
                    "id": artifact_id,
                    "definition_id": definition_id,
                    "run_id": run_id,
                    "attempt_id": permit.request_attempt_id,
                    "checksum": "c" * 64,
                    "now": NOW,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO provider_audit_events "
                    "(id, provider_definition_id, sync_run_id, actor_type, action_code, "
                    "decision_code, safe_summary, event_checksum) VALUES "
                    "(:id, :definition_id, :run_id, 'GATE_B_SEC_PILOT', "
                    "'DATA_QUALITY_STOP', 'PASSED', :summary, :checksum)"
                ),
                {
                    "id": uuid4(),
                    "definition_id": definition_id,
                    "run_id": run_id,
                    "summary": canonical_provider_json(
                        {"provider": "SEC_EDGAR_PUBLIC_V1", "status": "PASSED"}
                    ),
                    "checksum": provider_checksum(
                        {"provider": "SEC_EDGAR_PUBLIC_V1", "status": "PASSED"}
                    ),
                },
            )
        with Session(engine) as session:
            view = module.get_gate_b_audit_view(session, run_id)
        assert view is not None
        assert view.artifact_id == artifact_id
        assert view.authorization_id == execution.authorization_id
        assert view.request_attempt_id == permit.request_attempt_id
        assert view.plan_checksum == execution.plan_checksum
        assert view.provider == "SEC_EDGAR_PUBLIC_V1"
