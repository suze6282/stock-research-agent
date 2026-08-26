from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from stock_research_agent.domain.live_evidence.enums import ConsumptionState
from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    GateBAuthorizationValidation,
)
from stock_research_agent.domain.live_evidence.gate_b_pilot import (
    AuthorizedSecGateBOfflineApplication,
    CommittedSecSettlement,
    LiveValidationResult,
    SecDataQualityStopService,
    SecGateBPilotApplication,
)
from stock_research_agent.domain.live_evidence.schemas import ConsumptionSettlementRequest
from stock_research_agent.domain.providers.canonical import (
    canonical_provider_json,
    provider_checksum,
)
from stock_research_agent.domain.providers.quality import ProviderDataQualityValidator
from stock_research_agent.providers.sec_edgar.retry import SecAttemptKind
from tests.integration.test_gate_b_sec_pilot_postgres import (
    NOW,
    _request,
    _reservation_schema,
)
from tests.unit.test_gate_b_corrective_orchestration_red import (
    _contact_reference,
    _context_for,
    _Documents,
    _exact_plan,
    _RecordingTransport,
)
from tests.unit.test_sec_gate_b_pilot import _adapter

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required"),
]


def _install_approval_and_grant_events(engine: Engine, execution: object) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE live_execution_approvals ("
                "id uuid PRIMARY KEY, authorization_id uuid NOT NULL, "
                "plan_id uuid NOT NULL, plan_checksum varchar(64) NOT NULL, "
                "state varchar(16) NOT NULL, expires_at timestamptz NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE live_authorization_events ("
                "id uuid PRIMARY KEY, authorization_id uuid NOT NULL, sequence integer NOT NULL, "
                "event_type varchar(32) NOT NULL, UNIQUE (authorization_id, sequence))"
            )
        )
        connection.execute(
            text(
                "INSERT INTO live_execution_approvals "
                "(id, authorization_id, plan_id, plan_checksum, state, expires_at) "
                "VALUES (:id, :authorization_id, :plan_id, :plan_checksum, 'VALID', "
                ":expires_at)"
            ),
            {
                "id": execution.approval_id,
                "authorization_id": execution.authorization_id,
                "plan_id": execution.plan_id,
                "plan_checksum": execution.plan_checksum,
                "expires_at": NOW.replace(hour=1),
            },
        )
        connection.execute(
            text(
                "INSERT INTO live_authorization_events "
                "(id, authorization_id, sequence, event_type) VALUES "
                "(:first, :authorization_id, 1, 'APPROVE'), "
                "(:second, :authorization_id, 2, 'ACTIVATE')"
            ),
            {
                "first": uuid4(),
                "second": uuid4(),
                "authorization_id": execution.authorization_id,
            },
        )


def _port(module: object, sessions: object, execution: object, run_id: UUID) -> object:
    return module.SqlAlchemySecAttemptReservationPort(  # type: ignore[attr-defined]
        session_factory=sessions,
        execution=execution,
        sync_run_id=run_id,
        reserved_bytes=1024,
        clock=lambda: NOW,
    )


def _start_port(module: object, sessions: object, execution: object, run_id: UUID) -> object:
    validation = GateBAuthorizationValidation.model_validate(  # type: ignore[attr-defined]
        execution.model_dump(mode="python")
    )
    return module.SqlAlchemySecAttemptReservationPort(  # type: ignore[attr-defined]
        session_factory=sessions,
        execution=validation,
        sync_run_id=run_id,
        reserved_bytes=1024,
        clock=lambda: NOW,
    )


def _terminal_store(module: object, sessions: object, execution: object, run_id: UUID) -> object:
    return module.SqlAlchemySecTerminalStore(  # type: ignore[attr-defined]
        session_factory=sessions,
        execution=execution,
        provider_definition_id=uuid4(),
        provider_capability_id=uuid4(),
        sync_run_id=run_id,
        started_at=NOW,
        expires_at=NOW.replace(hour=1),
        max_requests=3,
        max_bytes=26_214_400,
        clock=lambda: NOW,
    )


def _terminal_result(**updates: object) -> LiveValidationResult:
    values: dict[str, object] = {
        "status": "PASSED",
        "artifact_id": uuid4(),
        "manifest_id": uuid4(),
        "request_attempt_id": uuid4(),
        "document_version_id": uuid4(),
        "citation_ids": (uuid4(),),
        "data_quality_issue_count": 0,
    }
    values.update(updates)
    return LiveValidationResult(**values)


def _install_complete_terminal_lineage(engine: Engine, run_id: UUID) -> tuple[UUID, UUID]:
    definition_id = uuid4()
    primary_attempt_id = uuid4()
    primary_artifact_id = uuid4()
    with engine.begin() as connection:
        for attempt_number, slice_id in enumerate(
            ("SEC_SUBMISSIONS", "SEC_FILING_INDEX", "SEC_PRIMARY_DOCUMENT"),
            start=1,
        ):
            attempt_id = primary_attempt_id if attempt_number == 3 else uuid4()
            artifact_id = primary_artifact_id if attempt_number == 3 else uuid4()
            connection.execute(
                text(
                    "INSERT INTO provider_request_attempts "
                    "(id, sync_run_id, slice_id, attempt_number, status, endpoint_id, "
                    "response_bytes, started_at, completed_at) VALUES "
                    "(:id, :run_id, :slice_id, :attempt_number, 'COMPLETED', "
                    "'SEC_GATE_B_RESOURCE', 128, :now, :now)"
                ),
                {
                    "id": attempt_id,
                    "run_id": run_id,
                    "slice_id": slice_id,
                    "attempt_number": attempt_number,
                    "now": NOW,
                },
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
                    "attempt_id": attempt_id,
                    "checksum": str(attempt_number) * 64,
                    "now": NOW,
                },
            )
    return primary_attempt_id, primary_artifact_id


class _DatabaseRecordingSettlement:
    def __init__(self, engine: Engine, definition_id: UUID) -> None:
        self._engine = engine
        self._definition_id = definition_id

    def settle(self, value: object, attempt: object) -> CommittedSecSettlement:
        artifact_id = value.artifact_id  # type: ignore[attr-defined]
        manifest_id = uuid4()
        request_attempt_id = value.request_attempt_id  # type: ignore[attr-defined]
        body = value.body  # type: ignore[attr-defined]
        batch = value.batch  # type: ignore[attr-defined]
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE provider_request_attempts SET status='COMPLETED', "
                    "response_status_code=200, response_bytes=:response_bytes, completed_at=:now "
                    "WHERE id=:request_attempt_id"
                ),
                {
                    "request_attempt_id": request_attempt_id,
                    "response_bytes": len(body),
                    "now": NOW,
                },
            )
            connection.execute(
                text(
                    "UPDATE live_authorization_consumptions SET state='SETTLED', "
                    "actual_bytes=:response_bytes, socket_opened=true, settled_at=:now "
                    "WHERE request_attempt_id=:request_attempt_id"
                ),
                {
                    "request_attempt_id": request_attempt_id,
                    "response_bytes": len(body),
                    "now": NOW,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO provider_raw_artifacts "
                    "(id, provider_definition_id, sync_run_id, request_attempt_id, "
                    "source_checksum, acquired_at) VALUES "
                    "(:id, :definition_id, :run_id, :request_attempt_id, :checksum, :now)"
                ),
                {
                    "id": artifact_id,
                    "definition_id": self._definition_id,
                    "run_id": value.context.sync_run_id,  # type: ignore[attr-defined]
                    "request_attempt_id": request_attempt_id,
                    "checksum": value.source_checksum,  # type: ignore[attr-defined]
                    "now": NOW,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO provider_ingestion_manifests "
                    "(id, raw_artifact_id, sync_run_id, batch_checksum, manifest_checksum, "
                    "adapter_version, parser_version, schema_version, record_count, "
                    "warning_codes, created_at) VALUES "
                    "(:id, :artifact_id, :run_id, :batch_checksum, :manifest_checksum, "
                    "'1.0.0', '1.0.0', '1.0.0', :record_count, CAST('[]' AS jsonb), :now)"
                ),
                {
                    "id": manifest_id,
                    "artifact_id": artifact_id,
                    "run_id": value.context.sync_run_id,  # type: ignore[attr-defined]
                    "batch_checksum": batch.batch_checksum,
                    "manifest_checksum": batch.manifest_checksum,
                    "record_count": len(batch.records),
                    "now": NOW,
                },
            )
        return CommittedSecSettlement(
            artifact_id=artifact_id,
            manifest_id=manifest_id,
            request_attempt_id=request_attempt_id,
            storage_uri=f"blob://offline/{artifact_id}",
            content_checksum=value.source_checksum,  # type: ignore[attr-defined]
            manifest_checksum=batch.manifest_checksum,
        )

    def settle_failure(self, attempt: object) -> None:
        raise AssertionError(f"unexpected failure settlement: {attempt!r}")


def test_red_051_concurrent_single_use_approval_starts_exactly_once() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        _install_approval_and_grant_events(engine, execution)
        barrier = Barrier(2)

        def start(slice_id: str) -> str:
            barrier.wait(timeout=5)
            try:
                _start_port(module, sessions, execution, run_id).start_execution(
                    _request(execution, slice_id, 1)
                )
                return "STARTED"
            except LiveEvidenceValidationError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = tuple(executor.map(start, ("SEC_SUBMISSIONS", "SEC_FILING_INDEX")))

        with engine.connect() as connection:
            approval_state = connection.scalar(
                text("SELECT state FROM live_execution_approvals WHERE id=:id"),
                {"id": execution.approval_id},
            )
            consume_events = connection.scalar(
                text(
                    "SELECT count(*) FROM live_authorization_events "
                    "WHERE authorization_id=:id AND event_type='CONSUME'"
                ),
                {"id": execution.authorization_id},
            )
            attempts = connection.scalar(text("SELECT count(*) FROM provider_request_attempts"))

        assert results.count("STARTED") == 1
        assert results.count("EXEC_APPROVAL_REPLAYED") == 1
        assert approval_state == "CONSUMED"
        assert consume_events == 1
        assert attempts == 1


def test_red_052a_execution_start_conflict_has_stable_domain_failure_boundary() -> None:
    """GBR-01: the production reservation boundary must not leak repository errors."""

    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        _install_approval_and_grant_events(engine, execution)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO provider_request_attempts "
                    "(id, sync_run_id, slice_id, attempt_number, status, endpoint_id, "
                    "response_bytes, started_at) VALUES "
                    "(:id, :run_id, 'SEC_SUBMISSIONS', 1, 'PENDING', "
                    "'SEC_SUBMISSIONS', 0, :now)"
                ),
                {"id": uuid4(), "run_id": run_id, "now": NOW},
            )

        with pytest.raises(LiveEvidenceValidationError, match="PROVIDER_ATTEMPT_CONFLICT"):
            _start_port(module, sessions, execution, run_id).start_execution(
                _request(execution, "SEC_SUBMISSIONS", 1)
            )


def test_red_052b_execution_start_failure_rolls_back_all_start_lineage() -> None:
    """GBR-01: a pre-commit conflict must leave no partial execution-start lineage."""

    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        _install_approval_and_grant_events(engine, execution)
        existing_attempt_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO provider_request_attempts "
                    "(id, sync_run_id, slice_id, attempt_number, status, endpoint_id, "
                    "response_bytes, started_at) VALUES "
                    "(:id, :run_id, 'SEC_SUBMISSIONS', 1, 'PENDING', "
                    "'SEC_SUBMISSIONS', 0, :now)"
                ),
                {"id": existing_attempt_id, "run_id": run_id, "now": NOW},
            )

        with pytest.raises(LiveEvidenceValidationError, match="PROVIDER_ATTEMPT_CONFLICT"):
            _start_port(module, sessions, execution, run_id).start_execution(
                _request(execution, "SEC_SUBMISSIONS", 1)
            )

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT state FROM live_execution_approvals")) == "VALID"
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM live_authorization_events WHERE event_type='CONSUME'"
                    )
                )
                == 0
            )
            assert (
                connection.scalar(text("SELECT count(*) FROM live_authorization_consumptions")) == 0
            )
            assert connection.scalar(text("SELECT count(*) FROM provider_request_attempts")) == 1
            assert connection.scalar(text("SELECT id FROM provider_request_attempts")) == (
                existing_attempt_id
            )


def test_red_052c_committed_execution_start_persists_consumed_lineage() -> None:
    """GBR-01: a committed initial reservation must retain authoritative consumption."""

    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        _install_approval_and_grant_events(engine, execution)
        start = _start_port(module, sessions, execution, run_id).start_execution(
            _request(execution, "SEC_SUBMISSIONS", 1)
        )
        permit = start.initial_permit

        with engine.connect() as connection:
            persisted_state = (
                connection.scalar(text("SELECT state FROM live_execution_approvals")),
                connection.scalar(
                    text(
                        "SELECT count(*) FROM live_authorization_events WHERE event_type='CONSUME'"
                    )
                ),
                connection.scalar(text("SELECT count(*) FROM live_authorization_consumptions")),
                connection.scalar(
                    text(
                        "SELECT count(*) FROM provider_request_attempts "
                        "WHERE id=:request_attempt_id AND status='PENDING'"
                    ),
                    {"request_attempt_id": permit.request_attempt_id},
                ),
            )

        assert persisted_state == ("CONSUMED", 1, 1, 1)


def test_red_053_abandoned_request_reservation_does_not_restore_capacity() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        with engine.begin() as connection:
            connection.execute(text("UPDATE live_authorization_grants SET request_limit=1"))
        port = _port(module, sessions, execution, run_id)
        permit = port.reserve(_request(execution, "SEC_SUBMISSIONS", 1))
        with sessions.begin() as session:
            module.settle_consumption(
                session,
                ConsumptionSettlementRequest(
                    authorization_id=execution.authorization_id,
                    request_attempt_id=permit.request_attempt_id,
                    actual_bytes=0,
                    socket_opened=False,
                    state=ConsumptionState.ABANDONED,
                    settled_at=NOW,
                ),
            )

        with pytest.raises(LiveEvidenceValidationError, match="SEC_ATTEMPT_BUDGET_EXHAUSTED"):
            port.reserve(_request(execution, "SEC_FILING_INDEX", 2))


def test_red_053_abandoned_retry_keeps_plan_global_retry_token_and_attempt_identity() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (_engine, sessions, execution, run_id):
        port = _port(module, sessions, execution, run_id)
        port.reserve(_request(execution, "SEC_SUBMISSIONS", 1))
        retry = port.reserve(_request(execution, "SEC_SUBMISSIONS", 2, kind=SecAttemptKind.RETRY))
        with sessions.begin() as session:
            module.settle_consumption(
                session,
                ConsumptionSettlementRequest(
                    authorization_id=execution.authorization_id,
                    request_attempt_id=retry.request_attempt_id,
                    actual_bytes=0,
                    socket_opened=False,
                    state=ConsumptionState.ABANDONED,
                    settled_at=NOW,
                ),
            )
        with pytest.raises(LiveEvidenceValidationError, match="SEC_RETRY_BUDGET_EXHAUSTED"):
            port.reserve(_request(execution, "SEC_SUBMISSIONS", 3, kind=SecAttemptKind.RETRY))


def test_red_054_abandoned_run_cannot_restart_with_the_same_approval() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        _install_approval_and_grant_events(engine, execution)
        first_port = _start_port(module, sessions, execution, run_id)
        start = first_port.start_execution(_request(execution, "SEC_SUBMISSIONS", 1))
        permit = start.initial_permit
        with sessions.begin() as session:
            module.settle_consumption(
                session,
                ConsumptionSettlementRequest(
                    authorization_id=execution.authorization_id,
                    request_attempt_id=permit.request_attempt_id,
                    actual_bytes=0,
                    socket_opened=False,
                    state=ConsumptionState.ABANDONED,
                    settled_at=NOW,
                ),
            )
        restarted_run_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO provider_sync_runs (id, sync_plan_id) VALUES (:run_id, :plan_id)"
                ),
                {"run_id": restarted_run_id, "plan_id": execution.plan_id},
            )

        with pytest.raises(
            LiveEvidenceValidationError,
            match="AUTHORIZATION_ALREADY_CONSUMED|EXEC_APPROVAL_REPLAYED",
        ):
            _start_port(module, sessions, execution, restarted_run_id).start_execution(
                _request(execution, "SEC_SUBMISSIONS", 1)
            )


def test_red_055_audit_projection_returns_all_attempts_and_artifacts() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        definition_id = uuid4()
        port = _port(module, sessions, execution, run_id)
        permits = tuple(
            port.reserve(_request(execution, slice_id, attempt_number))
            for attempt_number, slice_id in enumerate(
                ("SEC_SUBMISSIONS", "SEC_FILING_INDEX", "SEC_PRIMARY_DOCUMENT"),
                start=1,
            )
        )
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
                    "response_bytes=128, response_status_code=200, completed_at=:now"
                ),
                {"now": NOW},
            )
            for index, permit in enumerate(permits):
                connection.execute(
                    text(
                        "INSERT INTO provider_raw_artifacts "
                        "(id, provider_definition_id, sync_run_id, request_attempt_id, "
                        "source_checksum, acquired_at) VALUES "
                        "(:id, :definition_id, :run_id, :attempt_id, :checksum, :now)"
                    ),
                    {
                        "id": uuid4(),
                        "definition_id": definition_id,
                        "run_id": run_id,
                        "attempt_id": permit.request_attempt_id,
                        "checksum": f"{index + 1}" * 64,
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
        assert len(getattr(view, "attempts", ())) == 3
        assert len(getattr(view, "artifacts", ())) == 3
        assert "SECRET_SENTINEL_DO_NOT_LOG" not in repr(view)


def test_red_056_equivalent_terminal_replay_returns_existing_ids_without_inserts() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        primary_attempt_id, primary_artifact_id = _install_complete_terminal_lineage(engine, run_id)
        store = _terminal_store(module, sessions, execution, run_id)
        result = _terminal_result(
            request_attempt_id=primary_attempt_id,
            artifact_id=primary_artifact_id,
        )

        first = store.commit(result, ())
        second = store.commit(result, ())

        with engine.connect() as connection:
            terminal_rows = connection.scalar(
                text("SELECT count(*) FROM provider_live_validation_runs")
            )
            audit_rows = connection.scalar(
                text(
                    "SELECT count(*) FROM provider_audit_events "
                    "WHERE action_code='DATA_QUALITY_STOP'"
                )
            )
        assert second == first
        assert terminal_rows == audit_rows == 1


def test_red_056_conflicting_terminal_replay_fails_closed() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        primary_attempt_id, primary_artifact_id = _install_complete_terminal_lineage(engine, run_id)
        store = _terminal_store(module, sessions, execution, run_id)
        result = _terminal_result(
            request_attempt_id=primary_attempt_id,
            artifact_id=primary_artifact_id,
        )
        store.commit(result, ())

        with pytest.raises(LiveEvidenceValidationError, match="GATE_B_TERMINAL_CONFLICT"):
            store.commit(result.model_copy(update={"status": "BLOCKED"}), ())


def test_red_056_concurrent_identical_terminal_commit_creates_one_terminal() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        primary_attempt_id, primary_artifact_id = _install_complete_terminal_lineage(engine, run_id)
        result = _terminal_result(
            request_attempt_id=primary_attempt_id,
            artifact_id=primary_artifact_id,
        )
        barrier = Barrier(2)

        def commit() -> UUID:
            barrier.wait(timeout=5)
            return _terminal_store(module, sessions, execution, run_id).commit(result, ())

        with ThreadPoolExecutor(max_workers=2) as executor:
            ids = tuple(executor.map(lambda _index: commit(), range(2)))
        with engine.connect() as connection:
            count = connection.scalar(text("SELECT count(*) FROM provider_live_validation_runs"))
        assert ids[0] == ids[1]
        assert count == 1


def test_red_059_audit_retains_prior_artifact_and_later_failed_attempt() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        definition_id = uuid4()
        port = _port(module, sessions, execution, run_id)
        first = port.reserve(_request(execution, "SEC_SUBMISSIONS", 1))
        second = port.reserve(_request(execution, "SEC_FILING_INDEX", 2))
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
                    "actual_bytes=CASE WHEN request_attempt_id=:first THEN 128 ELSE 0 END, "
                    "socket_opened=true, settled_at=:now"
                ),
                {"first": first.request_attempt_id, "now": NOW},
            )
            connection.execute(
                text(
                    "UPDATE provider_request_attempts SET "
                    "status=CASE WHEN id=:first THEN 'COMPLETED' ELSE 'BLOCKED' END, "
                    "response_bytes=CASE WHEN id=:first THEN 128 ELSE 0 END, completed_at=:now"
                ),
                {"first": first.request_attempt_id, "now": NOW},
            )
            connection.execute(
                text(
                    "INSERT INTO provider_raw_artifacts "
                    "(id, provider_definition_id, sync_run_id, request_attempt_id, "
                    "source_checksum, acquired_at) VALUES "
                    "(:id, :definition_id, :run_id, :attempt_id, :checksum, :now)"
                ),
                {
                    "id": uuid4(),
                    "definition_id": definition_id,
                    "run_id": run_id,
                    "attempt_id": first.request_attempt_id,
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
                    "'DATA_QUALITY_STOP', 'BLOCKED', :summary, :checksum)"
                ),
                {
                    "id": uuid4(),
                    "definition_id": definition_id,
                    "run_id": run_id,
                    "summary": canonical_provider_json(
                        {"provider": "SEC_EDGAR_PUBLIC_V1", "status": "BLOCKED"}
                    ),
                    "checksum": provider_checksum(
                        {"provider": "SEC_EDGAR_PUBLIC_V1", "status": "BLOCKED"}
                    ),
                },
            )
        with Session(engine) as session:
            view = module.get_gate_b_audit_view(session, run_id)

        assert view is not None
        attempt_ids = {item.request_attempt_id for item in getattr(view, "attempts", ())}
        artifact_attempt_ids = {item.request_attempt_id for item in getattr(view, "artifacts", ())}
        assert attempt_ids == {first.request_attempt_id, second.request_attempt_id}
        assert artifact_attempt_ids == {first.request_attempt_id}


def test_red_060_incomplete_resource_set_cannot_commit_passed_terminal() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (_engine, sessions, execution, run_id):
        store = _terminal_store(module, sessions, execution, run_id)

        with pytest.raises(
            LiveEvidenceValidationError,
            match="GATE_B_RESOURCE_SET_INCOMPLETE",
        ):
            store.commit(_terminal_result(status="PASSED"), ())


def test_red_061_offline_production_root_returns_real_postgres_audit_projection() -> None:
    module = pytest.importorskip("stock_research_agent.db.repositories.live_evidence")
    with _reservation_schema() as (engine, sessions, execution, run_id):
        _install_approval_and_grant_events(engine, execution)
        definition_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE provider_ingestion_manifests ("
                    "id uuid PRIMARY KEY, raw_artifact_id uuid NOT NULL, "
                    "sync_run_id uuid NOT NULL, "
                    "batch_checksum varchar(64) NOT NULL, manifest_checksum varchar(64) NOT NULL, "
                    "adapter_version varchar(32) NOT NULL, parser_version varchar(32) NOT NULL, "
                    "schema_version varchar(64) NOT NULL, record_count integer NOT NULL, "
                    "warning_codes jsonb NOT NULL, created_at timestamptz NOT NULL)"
                )
            )
            connection.execute(
                text("INSERT INTO provider_definitions (id, code) VALUES (:id, :code)"),
                {"id": definition_id, "code": "SEC_EDGAR_PUBLIC_V1"},
            )
        execution_start = _start_port(module, sessions, execution, run_id)
        terminal_store = _terminal_store(module, sessions, execution, run_id)

        class _VerifiedTerminalStore:
            def commit(self, result: object, issues: tuple[object, ...]) -> UUID:
                with engine.connect() as connection:
                    assert (
                        connection.scalar(text("SELECT count(*) FROM provider_ingestion_manifests"))
                        == 3
                    )
                return terminal_store.commit(result, issues)  # type: ignore[arg-type]

        pilot = SecGateBPilotApplication(
            transport=_RecordingTransport(),
            adapter=_adapter(),
            settlement=_DatabaseRecordingSettlement(engine, definition_id),  # type: ignore[arg-type]
            documents=_Documents(),
            data_quality=SecDataQualityStopService(
                validator=ProviderDataQualityValidator(),
                terminal_store=_VerifiedTerminalStore(),
            ),
            artifact_id_factory=uuid4,
            reservations=execution_start,
            ingestion_context_factory=lambda resource: _context_for(resource).model_copy(
                update={"sync_run_id": run_id}
            ),
        )
        application = AuthorizedSecGateBOfflineApplication(
            execution_start=execution_start,
            pilot=pilot,
            audit_repository=module.SqlAlchemyGateBAuditRepository(
                session_factory=sessions,
                sync_run_id=run_id,
            ),
        )

        plan = _exact_plan(include_artifact_kinds=True).model_copy(  # type: ignore[attr-defined]
            update={"id": execution.plan_id, "plan_checksum": execution.plan_checksum}
        )
        audit = application.execute_authorized(
            GateBAuthorizationValidation.model_validate(execution.model_dump(mode="python")),
            plan=plan,
            contact_reference=_contact_reference(),
        )

        assert tuple(resource.slice_id for resource in audit.resources) == (
            "SEC_SUBMISSIONS",
            "SEC_FILING_INDEX",
            "SEC_PRIMARY_DOCUMENT",
        )
        assert len(audit.attempts) == 3
        assert len(audit.artifacts) == 3
        assert len(audit.manifests) == 3
        assert audit.document_version_id is not None
        assert audit.citation_ids
        assert audit.terminal_status == "PASSED"
        assert audit.terminal_stage == "DATA_QUALITY"
