"""Transaction-neutral persistence for controlled live-evidence budgets."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session, SessionTransaction

from stock_research_agent.db.models.providers import (
    ProviderAuditEvent,
    ProviderDataQualityIssue,
    ProviderLiveValidationRun,
)
from stock_research_agent.db.repositories.providers import (
    ProviderRepositoryConflict,
    SqlAlchemyProviderArtifactRepository,
    SqlAlchemyProviderSyncRepository,
)
from stock_research_agent.domain.live_evidence.authorization import (
    AuthorizationConsumption,
    AuthorizationStateMachine,
)
from stock_research_agent.domain.live_evidence.enums import (
    ConsumptionState,
    ExecutionApprovalState,
    LiveAuthorizationEventType,
    LiveAuthorizationState,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizedGateBExecution,
    GateBAuthorizationValidation,
)
from stock_research_agent.domain.live_evidence.gate_b_pilot import (
    GateBAuditArtifactView,
    GateBAuditAttemptView,
    GateBAuditConsumptionView,
    GateBAuditDataQualityIssueView,
    GateBAuditManifestView,
    GateBAuditResourceView,
    GateBAuditView,
    LiveValidationResult,
)
from stock_research_agent.domain.live_evidence.schemas import (
    ConsumptionReservation,
    ConsumptionReservationRequest,
    ConsumptionSettlementRequest,
    LiveAuthorizationConsumptionRecord,
)
from stock_research_agent.domain.providers.artifacts import (
    ProviderIngestionManifestRecord,
    ProviderIngestionManifestWrite,
    ProviderRawArtifactReservation,
)
from stock_research_agent.domain.providers.canonical import (
    canonical_provider_json,
    provider_checksum,
)
from stock_research_agent.domain.providers.quality import ProviderQualityIssue
from stock_research_agent.domain.providers.sync import (
    ProviderRequestAttemptSettlement,
)
from stock_research_agent.providers.sec_edgar.retry import (
    SecAttemptKind,
    SecAttemptPermit,
    SecAttemptReservationRequest,
    SecExecutionStartResult,
)

_QUERY_RESOURCES = {
    "get_live_authorization": ("live_authorization_grants", "id", False),
    "list_live_authorization_events": (
        "live_authorization_events",
        "authorization_id",
        True,
    ),
    "list_live_authorization_consumptions": (
        "live_authorization_consumptions",
        "authorization_id",
        True,
    ),
    "get_live_execution_approval": ("live_execution_approvals", "id", False),
    "get_manual_evidence_import": ("manual_evidence_import_requests", "id", False),
    "get_evidence_ingestion_manifest": ("evidence_ingestion_manifests", "id", False),
    "get_real_company_validation_run": ("real_company_validation_runs", "id", False),
    "list_end_to_end_validations": (
        "end_to_end_research_validations",
        "validation_run_id",
        True,
    ),
    "get_live_incident": ("live_incidents", "id", False),
    "list_live_incident_events": ("live_incident_events", "incident_id", True),
}


class SqlAlchemyLiveEvidenceQueryRepository:
    """Return only safe identity/timestamp projections from an exact allowlist."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def query_view(
        self,
        resource_type: str,
        resource_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> dict[str, JsonValue] | None:
        resource = _QUERY_RESOURCES.get(resource_type)
        if resource is None or not 1 <= limit <= 100 or not 0 <= offset <= 100_000:
            return None
        table, key, many = resource
        rows = (
            self._session.execute(
                text(
                    f"SELECT id::text AS id, created_at::text AS created_at FROM {table} "
                    f"WHERE {key} = :resource_id ORDER BY created_at, id "
                    "LIMIT :limit OFFSET :offset"
                ),
                {"resource_id": resource_id, "limit": limit, "offset": offset},
            )
            .mappings()
            .all()
        )
        if not rows and not many:
            return None
        items: list[JsonValue] = [
            {"id": str(row["id"]), "created_at": str(row["created_at"])} for row in rows
        ]
        if many:
            return {
                "resource_type": resource_type,
                "items": items,
                "limit": limit,
                "offset": offset,
            }
        first = items[0]
        if not isinstance(first, dict):
            return None
        return {"resource_type": resource_type, **first}


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def reserve_consumption(
    session: Session,
    request: ConsumptionReservationRequest,
) -> ConsumptionReservation:
    """Reserve one request while holding the authorization row lock."""
    request_limit = session.scalar(
        text(
            "SELECT request_limit FROM live_authorization_grants "
            "WHERE id = :authorization_id FOR UPDATE"
        ),
        {"authorization_id": request.authorization_id},
    )
    if request_limit is None:
        raise LiveEvidenceValidationError("AUTH_RESERVATION_INVALID")

    existing_row = (
        session.execute(
            text(
                "SELECT id, authorization_id, request_attempt_id, reserved_bytes, "
                "reserved_at, state FROM live_authorization_consumptions "
                "WHERE authorization_id = :authorization_id "
                "AND request_attempt_id = :request_attempt_id"
            ),
            {
                "authorization_id": request.authorization_id,
                "request_attempt_id": request.request_attempt_id,
            },
        )
        .mappings()
        .one_or_none()
    )
    if existing_row is not None:
        existing = ConsumptionReservation(
            id=existing_row["id"],
            authorization_id=existing_row["authorization_id"],
            request_attempt_id=existing_row["request_attempt_id"],
            reserved_bytes=existing_row["reserved_bytes"],
            reserved_at=_utc(existing_row["reserved_at"]),
            state=ConsumptionState(existing_row["state"]),
        )
        return AuthorizationConsumption.reserve(request, existing=existing)

    consumed_requests = session.scalar(
        text(
            "SELECT count(*) FROM live_authorization_consumptions "
            "WHERE authorization_id = :authorization_id"
        ),
        {"authorization_id": request.authorization_id},
    )
    if consumed_requests is None or consumed_requests >= request_limit:
        raise LiveEvidenceValidationError("AUTH_REQUEST_BUDGET_EXCEEDED")

    reservation = AuthorizationConsumption.reserve(request)
    session.execute(
        text(
            "INSERT INTO live_authorization_consumptions "
            "(id, authorization_id, request_attempt_id, reserved_bytes, state, reserved_at) "
            "VALUES (:id, :authorization_id, :request_attempt_id, :reserved_bytes, "
            ":state, :reserved_at)"
        ),
        {
            "id": reservation.id,
            "authorization_id": reservation.authorization_id,
            "request_attempt_id": reservation.request_attempt_id,
            "reserved_bytes": reservation.reserved_bytes,
            "state": reservation.state.value,
            "reserved_at": reservation.reserved_at,
        },
    )
    return reservation


class SqlAlchemySecAttemptReservationPort:
    """Atomically commit a Gate B request permit before any network activity."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        execution: AuthorizedGateBExecution | GateBAuthorizationValidation,
        sync_run_id: UUID,
        reserved_bytes: int,
        clock: Callable[[], datetime],
    ) -> None:
        self._session_factory = session_factory
        self._execution = execution
        self._sync_run_id = sync_run_id
        self._reserved_bytes = reserved_bytes
        self._clock = clock

    def reserve(self, request: SecAttemptReservationRequest) -> SecAttemptPermit:
        if not isinstance(self._execution, AuthorizedGateBExecution):
            raise LiveEvidenceValidationError("SEC_EXECUTION_START_REQUIRED")
        self._require_scope(request)
        request_attempt_id = uuid4()
        try:
            with self._session_factory() as session, session.begin():
                self._reserve_attempt(session, request, request_attempt_id)
        except ProviderRepositoryConflict as error:
            raise LiveEvidenceValidationError(str(error)) from None
        return SecAttemptPermit(
            **request.model_dump(mode="python"),
            request_attempt_id=request_attempt_id,
        )

    def start_execution(
        self,
        request: SecAttemptReservationRequest,
    ) -> SecExecutionStartResult:
        """Consume one persisted approval and reserve its initial attempt atomically."""

        if not isinstance(self._execution, GateBAuthorizationValidation):
            raise LiveEvidenceValidationError("SEC_EXECUTION_START_VALIDATION_REQUIRED")
        if request.kind is not SecAttemptKind.INITIAL or request.attempt_number != 1:
            raise LiveEvidenceValidationError("SEC_EXECUTION_START_INITIAL_REQUIRED")
        self._require_scope(request)
        request_attempt_id = uuid4()
        try:
            with self._session_factory() as session, session.begin():
                self._lock_and_validate_execution_start(session)
                session.execute(
                    text(
                        "UPDATE live_execution_approvals SET state = 'CONSUMED' "
                        "WHERE id = :approval_id AND state = 'VALID'"
                    ),
                    {"approval_id": self._execution.approval_id},
                )
                consume_authorization(session, self._execution.authorization_id)
                self._reserve_attempt(session, request, request_attempt_id)
        except ProviderRepositoryConflict as error:
            raise LiveEvidenceValidationError(str(error)) from None

        execution = AuthorizedGateBExecution.model_validate(
            self._execution.model_dump(mode="python")
        )
        self._execution = execution
        return SecExecutionStartResult(
            execution=execution,
            initial_permit=SecAttemptPermit(
                **request.model_dump(mode="python"),
                request_attempt_id=request_attempt_id,
            ),
        )

    def _lock_and_validate_execution_start(self, session: Session) -> None:
        approval = (
            session.execute(
                text(
                    "SELECT authorization_id, plan_id, plan_checksum, state, expires_at "
                    "FROM live_execution_approvals WHERE id = :approval_id FOR UPDATE"
                ),
                {"approval_id": self._execution.approval_id},
            )
            .mappings()
            .one_or_none()
        )
        if approval is None:
            raise LiveEvidenceValidationError("EXEC_APPROVAL_INVALID")
        if approval["state"] == ExecutionApprovalState.CONSUMED.value:
            raise LiveEvidenceValidationError("EXEC_APPROVAL_REPLAYED")
        if approval["state"] != ExecutionApprovalState.VALID.value:
            raise LiveEvidenceValidationError("EXEC_APPROVAL_INVALID")
        if _utc(approval["expires_at"]) <= self._clock():
            raise LiveEvidenceValidationError("EXEC_APPROVAL_EXPIRED")
        if (
            approval["authorization_id"] != self._execution.authorization_id
            or approval["plan_id"] != self._execution.plan_id
            or approval["plan_checksum"] != self._execution.plan_checksum
        ):
            raise LiveEvidenceValidationError("EXEC_APPROVAL_PLAN_MISMATCH")

        grant = (
            session.execute(
                text(
                    "SELECT id, canonical_checksum, scope, expires_at "
                    "FROM live_authorization_grants "
                    "WHERE id = :authorization_id FOR UPDATE"
                ),
                {"authorization_id": self._execution.authorization_id},
            )
            .mappings()
            .one_or_none()
        )
        if grant is None:
            raise LiveEvidenceValidationError("AUTH_RESERVATION_INVALID")
        if (
            grant["canonical_checksum"] != self._execution.authorization_checksum
            or _utc(grant["expires_at"]) <= self._clock()
        ):
            raise LiveEvidenceValidationError("AUTH_RESERVATION_INVALID")
        scope = grant["scope"]
        if not isinstance(scope, dict) or (
            str(scope.get("security_id")) != str(self._execution.security_id)
            or str(scope.get("issuer_id")) != str(self._execution.issuer_id)
            or scope.get("provider_security_identifier")
            != self._execution.provider_security_identifier
        ):
            raise LiveEvidenceValidationError("AUTH_SECURITY_MISMATCH")

        plan_id = session.scalar(
            text("SELECT sync_plan_id FROM provider_sync_runs WHERE id = :sync_run_id FOR UPDATE"),
            {"sync_run_id": self._sync_run_id},
        )
        if plan_id != self._execution.plan_id:
            raise LiveEvidenceValidationError("SEC_SYNC_RUN_PLAN_MISMATCH")
        plan_checksum = session.scalar(
            text("SELECT plan_checksum FROM provider_sync_plans WHERE id = :plan_id"),
            {"plan_id": plan_id},
        )
        if plan_checksum != self._execution.plan_checksum:
            raise LiveEvidenceValidationError("EXEC_APPROVAL_PLAN_MISMATCH")

    def _reserve_attempt(
        self,
        session: Session,
        request: SecAttemptReservationRequest,
        request_attempt_id: UUID,
    ) -> None:
        try:
            reserve_consumption(
                session,
                ConsumptionReservationRequest(
                    authorization_id=request.authorization_id,
                    request_attempt_id=request_attempt_id,
                    reserved_bytes=self._reserved_bytes,
                    reserved_at=self._clock(),
                ),
            )
        except LiveEvidenceValidationError as error:
            if error.code == "AUTH_REQUEST_BUDGET_EXCEEDED":
                raise LiveEvidenceValidationError("SEC_ATTEMPT_BUDGET_EXHAUSTED") from None
            raise
        plan_binding = (
            session.execute(
                text(
                    "SELECT run.sync_plan_id, plan.plan_checksum, plan.slices "
                    "FROM provider_sync_runs AS run "
                    "JOIN provider_sync_plans AS plan ON plan.id = run.sync_plan_id "
                    "WHERE run.id = :sync_run_id FOR UPDATE OF run, plan"
                ),
                {"sync_run_id": self._sync_run_id},
            )
            .mappings()
            .one_or_none()
        )
        if plan_binding is None or plan_binding["sync_plan_id"] != request.plan_id:
            raise LiveEvidenceValidationError("SEC_SYNC_RUN_PLAN_MISMATCH")
        if plan_binding["plan_checksum"] != request.plan_checksum:
            raise LiveEvidenceValidationError("EXEC_APPROVAL_PLAN_MISMATCH")
        self._require_persisted_plan_resource(request, plan_binding["slices"])
        total_attempts, retry_attempts = session.execute(
            text(
                "SELECT count(*), count(*) - count(DISTINCT slice_id) "
                "FROM provider_request_attempts WHERE sync_run_id = :sync_run_id"
            ),
            {"sync_run_id": self._sync_run_id},
        ).one()
        if total_attempts >= 4:
            raise LiveEvidenceValidationError("SEC_ATTEMPT_BUDGET_EXHAUSTED")
        existing_identity = session.scalar(
            text(
                "SELECT count(*) FROM provider_request_attempts "
                "WHERE sync_run_id = :sync_run_id AND slice_id = :slice_id "
                "AND attempt_number = :attempt_number"
            ),
            {
                "sync_run_id": self._sync_run_id,
                "slice_id": request.slice_id,
                "attempt_number": request.attempt_number,
            },
        )
        if not existing_identity and request.attempt_number != total_attempts + 1:
            raise LiveEvidenceValidationError("SEC_ATTEMPT_SEQUENCE_INVALID")
        prior_slice_occurrences = session.scalar(
            text(
                "SELECT count(*) FROM provider_request_attempts "
                "WHERE sync_run_id = :sync_run_id AND slice_id = :slice_id "
                "AND attempt_number < :attempt_number"
            ),
            {
                "sync_run_id": self._sync_run_id,
                "slice_id": request.slice_id,
                "attempt_number": request.attempt_number,
            },
        )
        expected_kind = SecAttemptKind.RETRY if prior_slice_occurrences else SecAttemptKind.INITIAL
        if request.kind is not expected_kind:
            raise LiveEvidenceValidationError("SEC_ATTEMPT_RESERVATION_REQUIRED")
        if expected_kind is SecAttemptKind.RETRY and retry_attempts >= 1:
            raise LiveEvidenceValidationError("SEC_RETRY_BUDGET_EXHAUSTED")
        if request.attempt_number == 4:
            request_limit = session.scalar(
                text(
                    "SELECT request_limit FROM live_authorization_grants "
                    "WHERE id = :authorization_id"
                ),
                {"authorization_id": request.authorization_id},
            )
            if self._execution.provider != "SEC_EDGAR_PUBLIC_V1" or request_limit != 4:
                raise LiveEvidenceValidationError("SEC_ATTEMPT_BUDGET_EXHAUSTED")
        self._persist_gate_b_attempt(session, request, request_attempt_id)

    @staticmethod
    def _require_persisted_plan_resource(
        request: SecAttemptReservationRequest,
        plan_slices: object,
    ) -> None:
        if not isinstance(plan_slices, list):
            raise LiveEvidenceValidationError("SEC_ATTEMPT_RESERVATION_REQUIRED")
        matching_slices = tuple(
            item
            for item in plan_slices
            if isinstance(item, dict) and item.get("slice_id") == request.slice_id
        )
        if len(matching_slices) != 1:
            raise LiveEvidenceValidationError("SEC_ATTEMPT_RESERVATION_REQUIRED")
        parameters = matching_slices[0].get("request_parameters")
        if not isinstance(parameters, dict) or parameters.get("endpoint_id") != request.endpoint_id:
            raise LiveEvidenceValidationError("SEC_ATTEMPT_RESERVATION_REQUIRED")

    def _persist_gate_b_attempt(
        self,
        session: Session,
        request: SecAttemptReservationRequest,
        request_attempt_id: UUID,
    ) -> None:
        existing = session.scalar(
            text(
                "SELECT count(*) FROM provider_request_attempts "
                "WHERE id = :request_attempt_id OR ("
                "sync_run_id = :sync_run_id AND slice_id = :slice_id "
                "AND attempt_number = :attempt_number)"
            ),
            {
                "request_attempt_id": request_attempt_id,
                "sync_run_id": self._sync_run_id,
                "slice_id": request.slice_id,
                "attempt_number": request.attempt_number,
            },
        )
        if existing:
            raise ProviderRepositoryConflict("PROVIDER_ATTEMPT_CONFLICT")
        session.execute(
            text(
                "INSERT INTO provider_request_attempts "
                "(id, sync_run_id, slice_id, attempt_number, status, endpoint_id, "
                "response_bytes, started_at) VALUES "
                "(:id, :sync_run_id, :slice_id, :attempt_number, 'PENDING', "
                ":endpoint_id, 0, :started_at)"
            ),
            {
                "id": request_attempt_id,
                "sync_run_id": self._sync_run_id,
                "slice_id": request.slice_id,
                "attempt_number": request.attempt_number,
                "endpoint_id": request.endpoint_id,
                "started_at": self._clock(),
            },
        )

    def _require_scope(self, request: SecAttemptReservationRequest) -> None:
        if (
            request.authorization_id != self._execution.authorization_id
            or request.plan_id != self._execution.plan_id
            or request.plan_checksum != self._execution.plan_checksum
            or (request.attempt_number == 1 and request.kind is not SecAttemptKind.INITIAL)
        ):
            raise LiveEvidenceValidationError("SEC_ATTEMPT_RESERVATION_REQUIRED")


class SqlAlchemySecSettlementTransaction:
    """Own one short post-response transaction; never spans network activity."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._transaction: SessionTransaction | None = None

    def __enter__(self) -> SqlAlchemySecSettlementTransaction:
        self._session = self._session_factory()
        self._transaction = self._session.begin()
        self._transaction.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        assert self._session is not None and self._transaction is not None
        try:
            self._transaction.__exit__(exc_type, exc, traceback)
        finally:
            self._session.close()
            self._session = None
            self._transaction = None

    def settle_attempt(self, value: ProviderRequestAttemptSettlement) -> object:
        return SqlAlchemyProviderSyncRepository(self._require_session()).settle_attempt(value)

    def settle_consumption(self, value: ConsumptionSettlementRequest) -> object:
        return settle_consumption(self._require_session(), value)

    def add_artifact(self, value: ProviderRawArtifactReservation) -> object:
        return SqlAlchemyProviderArtifactRepository(self._require_session()).add_artifact_with_id(
            value
        )

    def add_manifest(
        self, value: ProviderIngestionManifestWrite
    ) -> ProviderIngestionManifestRecord:
        return SqlAlchemyProviderArtifactRepository(self._require_session()).add_manifest(value)

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("SEC_SETTLEMENT_TRANSACTION_NOT_OPEN")
        return self._session


class SqlAlchemySecTerminalStore:
    """Commit DQ issues, terminal validation, and one secret-free audit event."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        execution: AuthorizedGateBExecution,
        provider_definition_id: UUID,
        provider_capability_id: UUID,
        sync_run_id: UUID,
        started_at: datetime,
        expires_at: datetime,
        max_requests: int,
        max_bytes: int,
        clock: Callable[[], datetime],
    ) -> None:
        self._session_factory = session_factory
        self._execution = execution
        self._provider_definition_id = provider_definition_id
        self._provider_capability_id = provider_capability_id
        self._sync_run_id = sync_run_id
        self._started_at = started_at
        self._expires_at = expires_at
        self._max_requests = max_requests
        self._max_bytes = max_bytes
        self._clock = clock

    def commit(
        self,
        result: LiveValidationResult,
        issues: tuple[ProviderQualityIssue, ...],
    ) -> UUID:
        if result.data_quality_issue_count != len(issues):
            raise LiveEvidenceValidationError("GATE_B_TERMINAL_ISSUE_COUNT_MISMATCH")
        issue_projection = tuple(
            sorted(
                (
                    {
                        "rule_code": issue.rule.value,
                        "safe_detail": issue.safe_detail,
                        "severity": "MEDIUM",
                        "status": "OPEN",
                    }
                    for issue in issues
                ),
                key=lambda item: (item["rule_code"], item["safe_detail"]),
            )
        )
        terminal_identity = {
            "artifact_id": result.artifact_id,
            "approval_id": self._execution.approval_id,
            "authorization_id": self._execution.authorization_id,
            "citation_ids": result.citation_ids,
            "document_version_id": result.document_version_id,
            "failed_ordinal": result.failed_ordinal,
            "failed_slice_id": result.failed_slice_id,
            "issue_count": len(issue_projection),
            "issue_checksum": provider_checksum(issue_projection),
            "manifest_id": result.manifest_id,
            "plan_checksum": self._execution.plan_checksum,
            "provider": self._execution.provider,
            "request_attempt_id": result.request_attempt_id,
            "security_id": self._execution.security_id,
            "status": result.status,
            "stop_reason": result.stop_reason,
            "terminal_stage": result.terminal_stage,
            "warning_codes": result.warning_codes,
        }
        terminal_checksum = provider_checksum(terminal_identity)
        validation_id = uuid4()
        event_id = uuid4()
        with self._session_factory() as session, session.begin():
            locked_run_id = session.scalar(
                text("SELECT id FROM provider_sync_runs WHERE id = :sync_run_id FOR UPDATE"),
                {"sync_run_id": self._sync_run_id},
            )
            if locked_run_id is None:
                raise LiveEvidenceValidationError("GATE_B_SYNC_RUN_INVALID")
            existing_rows = (
                session.execute(
                    text(
                        "SELECT id, safe_summary, event_checksum FROM provider_audit_events "
                        "WHERE sync_run_id = :sync_run_id "
                        "AND action_code = 'DATA_QUALITY_STOP' "
                        "ORDER BY created_at, id LIMIT 2"
                    ),
                    {"sync_run_id": self._sync_run_id},
                )
                .mappings()
                .all()
            )
            if len(existing_rows) > 1:
                raise LiveEvidenceValidationError("GATE_B_TERMINAL_CONFLICT")
            if existing_rows:
                existing = existing_rows[0]
                existing_summary = _load_terminal_summary(
                    existing["safe_summary"], existing["event_checksum"]
                )
                if existing_summary.get("terminal_checksum") != terminal_checksum:
                    raise LiveEvidenceValidationError("GATE_B_TERMINAL_CONFLICT")
                return UUID(str(existing["id"]))

            if result.status == "PASSED":
                _require_complete_gate_b_resource_set(session, self._sync_run_id, result)

            consumed_requests, consumed_bytes = session.execute(
                text(
                    "SELECT count(*), coalesce(sum(actual_bytes), 0) "
                    "FROM live_authorization_consumptions "
                    "WHERE authorization_id = :authorization_id"
                ),
                {"authorization_id": self._execution.authorization_id},
            ).one()
            summary = {
                **terminal_identity,
                "terminal_checksum": terminal_checksum,
                "terminal_validation_id": validation_id,
            }
            if issues and result.manifest_id is None:
                raise LiveEvidenceValidationError("GATE_B_TERMINAL_MANIFEST_REQUIRED")
            for issue in issues:
                session.add(
                    ProviderDataQualityIssue(
                        sync_run_id=self._sync_run_id,
                        manifest_id=result.manifest_id,
                        rule_code=issue.rule.value,
                        severity="MEDIUM",
                        status="OPEN",
                        safe_detail=issue.safe_detail,
                    )
                )
            session.add(
                ProviderLiveValidationRun(
                    id=validation_id,
                    provider_definition_id=self._provider_definition_id,
                    provider_capability_id=self._provider_capability_id,
                    authorization_id=str(self._execution.authorization_id),
                    live_authorization_grant_id=self._execution.authorization_id,
                    status="PASS" if result.status == "PASSED" else "BLOCKED",
                    max_requests=self._max_requests,
                    max_bytes=self._max_bytes,
                    consumed_requests=consumed_requests,
                    consumed_bytes=consumed_bytes,
                    expires_at=self._expires_at,
                    started_at=self._started_at,
                    completed_at=self._clock(),
                )
            )
            session.add(
                ProviderAuditEvent(
                    id=event_id,
                    provider_definition_id=self._provider_definition_id,
                    sync_run_id=self._sync_run_id,
                    actor_type="GATE_B_SEC_PILOT",
                    action_code="DATA_QUALITY_STOP",
                    decision_code=result.status,
                    safe_summary=canonical_provider_json(summary),
                    event_checksum=provider_checksum(summary),
                )
            )
        return event_id


def _require_complete_gate_b_resource_set(
    session: Session,
    sync_run_id: UUID,
    result: LiveValidationResult,
) -> None:
    rows = (
        session.execute(
            text(
                "SELECT attempt.slice_id, attempt.id AS request_attempt_id, "
                "artifact.id AS artifact_id "
                "FROM provider_request_attempts attempt "
                "JOIN provider_raw_artifacts artifact ON artifact.request_attempt_id = attempt.id "
                "WHERE attempt.sync_run_id = :sync_run_id AND attempt.status = 'COMPLETED' "
                "ORDER BY attempt.attempt_number"
            ),
            {"sync_run_id": sync_run_id},
        )
        .mappings()
        .all()
    )
    if tuple(row["slice_id"] for row in rows) != (
        "SEC_SUBMISSIONS",
        "SEC_FILING_INDEX",
        "SEC_PRIMARY_DOCUMENT",
    ):
        raise LiveEvidenceValidationError("GATE_B_RESOURCE_SET_INCOMPLETE")
    primary = rows[-1]
    if (
        primary["request_attempt_id"] != result.request_attempt_id
        or primary["artifact_id"] != result.artifact_id
        or not result.citation_ids
    ):
        raise LiveEvidenceValidationError("GATE_B_RESOURCE_SET_INCOMPLETE")
    if _table_exists(session, "provider_ingestion_manifests"):
        manifest_count = session.scalar(
            text(
                "SELECT count(*) FROM provider_ingestion_manifests manifest "
                "JOIN provider_raw_artifacts artifact ON artifact.id = manifest.raw_artifact_id "
                "WHERE artifact.sync_run_id = :sync_run_id"
            ),
            {"sync_run_id": sync_run_id},
        )
        if manifest_count != 3:
            raise LiveEvidenceValidationError("GATE_B_RESOURCE_SET_INCOMPLETE")


def _load_terminal_summary(safe_summary: str, event_checksum: str) -> dict[str, object]:
    try:
        parsed = json.loads(safe_summary)
    except json.JSONDecodeError:
        raise LiveEvidenceValidationError("GATE_B_AUDIT_TERMINAL_INVALID") from None
    if not isinstance(parsed, dict) or provider_checksum(parsed) != event_checksum:
        raise LiveEvidenceValidationError("GATE_B_AUDIT_TERMINAL_INVALID")
    return parsed


def get_gate_b_audit_view(session: Session, sync_run_id: UUID) -> GateBAuditView | None:
    """Assemble a secret-free Gate B view from committed authoritative rows only."""

    root = (
        session.execute(
            text(
                "SELECT to_jsonb(run) AS run, to_jsonb(plan) AS plan "
                "FROM provider_sync_runs run "
                "JOIN provider_sync_plans plan ON plan.id = run.sync_plan_id "
                "WHERE run.id = :sync_run_id"
            ),
            {"sync_run_id": sync_run_id},
        )
        .mappings()
        .one_or_none()
    )
    if root is None:
        return None

    attempts = _bounded_payloads(
        session,
        "SELECT to_jsonb(attempt) FROM provider_request_attempts attempt "
        "WHERE sync_run_id = :sync_run_id "
        "ORDER BY attempt_number, started_at, id LIMIT 5",
        {"sync_run_id": sync_run_id},
        maximum=4,
    )
    if not attempts:
        return None
    attempt_ids = tuple(UUID(str(attempt["id"])) for attempt in attempts)
    consumptions = _bounded_payloads(
        session,
        "SELECT to_jsonb(consumption) FROM live_authorization_consumptions consumption "
        "WHERE request_attempt_id = ANY(:attempt_ids) "
        "ORDER BY reserved_at, id LIMIT 5",
        {"attempt_ids": list(attempt_ids)},
        maximum=4,
    )
    if not consumptions:
        return None
    authorization_ids = {UUID(str(item["authorization_id"])) for item in consumptions}
    if len(authorization_ids) != 1:
        raise LiveEvidenceValidationError("GATE_B_AUDIT_AUTHORIZATION_INVALID")
    authorization_id = authorization_ids.pop()
    grant = session.scalar(
        text(
            "SELECT to_jsonb(auth_grant) FROM live_authorization_grants auth_grant "
            "WHERE id = :authorization_id"
        ),
        {"authorization_id": authorization_id},
    )
    if not isinstance(grant, dict):
        raise LiveEvidenceValidationError("GATE_B_AUDIT_AUTHORIZATION_INVALID")
    scope = grant.get("scope")
    if not isinstance(scope, dict):
        raise LiveEvidenceValidationError("GATE_B_AUDIT_SCOPE_INVALID")
    candidate = {
        key: str(scope[key])
        for key in ("security_id", "issuer_id", "provider_security_identifier")
        if key in scope
    }
    if len(candidate) != 3:
        raise LiveEvidenceValidationError("GATE_B_AUDIT_SCOPE_INVALID")

    artifacts = _bounded_payloads(
        session,
        "SELECT to_jsonb(artifact) FROM provider_raw_artifacts artifact "
        "WHERE sync_run_id = :sync_run_id ORDER BY acquired_at, id LIMIT 4",
        {"sync_run_id": sync_run_id},
        maximum=3,
    )
    provider = None
    if artifacts:
        provider = session.scalar(
            text("SELECT code FROM provider_definitions WHERE id = :provider_definition_id"),
            {"provider_definition_id": artifacts[0]["provider_definition_id"]},
        )

    terminal_rows = (
        session.execute(
            text(
                "SELECT id, decision_code, safe_summary, event_checksum "
                "FROM provider_audit_events WHERE sync_run_id = :sync_run_id "
                "AND action_code = 'DATA_QUALITY_STOP' ORDER BY created_at, id LIMIT 2"
            ),
            {"sync_run_id": sync_run_id},
        )
        .mappings()
        .all()
    )
    if len(terminal_rows) > 1:
        raise LiveEvidenceValidationError("GATE_B_TERMINAL_CONFLICT")
    terminal = terminal_rows[0] if terminal_rows else None
    terminal_summary: dict[str, object] = {}
    if terminal is not None:
        terminal_summary = _load_terminal_summary(
            terminal["safe_summary"], terminal["event_checksum"]
        )
    if provider is None:
        provider = terminal_summary.get("provider")
    if not isinstance(provider, str):
        raise LiveEvidenceValidationError("GATE_B_AUDIT_PROVIDER_INVALID")

    manifests: list[dict[str, object]] = []
    if _table_exists(session, "provider_ingestion_manifests"):
        manifests = _bounded_payloads(
            session,
            "SELECT to_jsonb(manifest) FROM provider_ingestion_manifests manifest "
            "WHERE sync_run_id = :sync_run_id ORDER BY created_at, id LIMIT 4",
            {"sync_run_id": sync_run_id},
            maximum=3,
        )
    data_quality_issues: list[dict[str, object]] = []
    if _table_exists(session, "provider_data_quality_issues"):
        data_quality_issues = _bounded_payloads(
            session,
            "SELECT to_jsonb(issue) FROM provider_data_quality_issues issue "
            "WHERE sync_run_id = :sync_run_id "
            "ORDER BY created_at, rule_code, id LIMIT 1001",
            {"sync_run_id": sync_run_id},
            maximum=1000,
        )

    approval: dict[str, object] | None = None
    if _table_exists(session, "live_execution_approvals"):
        approval_id = terminal_summary.get("approval_id")
        if approval_id is not None:
            approval = session.scalar(
                text(
                    "SELECT to_jsonb(approval) FROM live_execution_approvals approval "
                    "WHERE id = :approval_id AND authorization_id = :authorization_id"
                ),
                {"approval_id": approval_id, "authorization_id": authorization_id},
            )

    event_types: tuple[str, ...] = ()
    if _table_exists(session, "live_authorization_events"):
        event_types = tuple(
            session.scalars(
                text(
                    "SELECT event_type FROM live_authorization_events "
                    "WHERE authorization_id = :authorization_id ORDER BY sequence"
                ),
                {"authorization_id": authorization_id},
            ).all()
        )
    grant_state = (
        AuthorizationStateMachine.replay(
            tuple(LiveAuthorizationEventType(value) for value in event_types)
        ).value
        if event_types
        else str(grant["status"])
    )

    plan = root["plan"]
    run = root["run"]
    if not isinstance(plan, dict) or not isinstance(run, dict):
        raise LiveEvidenceValidationError("GATE_B_AUDIT_PLAN_INVALID")
    slices = plan.get("slices")
    resources = _audit_resources(slices, attempts)
    seen_slices: set[str] = set()
    attempt_views_list: list[GateBAuditAttemptView] = []
    for item in attempts:
        slice_id = str(item["slice_id"])
        is_retry = slice_id in seen_slices
        attempt_views_list.append(_audit_attempt(item, consumptions, is_retry=is_retry))
        seen_slices.add(slice_id)
    attempt_views = tuple(attempt_views_list)
    consumption_views = tuple(_audit_consumption(item) for item in consumptions)
    artifact_views = tuple(_audit_artifact(item) for item in artifacts)
    manifest_views = tuple(_audit_manifest(item) for item in manifests)
    issue_views = tuple(_audit_issue(item) for item in data_quality_issues)

    document_version_id = _summary_uuid(terminal_summary, "document_version_id")
    document_checksum = None
    if document_version_id is not None and _table_exists(session, "document_versions"):
        document_checksum = session.scalar(
            text("SELECT checksum FROM document_versions WHERE id = :id"),
            {"id": document_version_id},
        )
        if document_checksum is None:
            raise LiveEvidenceValidationError("GATE_B_AUDIT_TERMINAL_INVALID")
    citation_ids = tuple(
        UUID(value) for value in _string_tuple(terminal_summary.get("citation_ids"))
    )
    parser_versions: tuple[str, ...] = ()
    sanitizer_versions: tuple[str, ...] = ()
    if document_version_id is not None and _table_exists(session, "document_parse_runs"):
        parse_rows = session.execute(
            text(
                "SELECT parser_version, sanitizer_version FROM document_parse_runs "
                "WHERE document_version_id = :id ORDER BY created_at, id LIMIT 10001"
            ),
            {"id": document_version_id},
        ).all()
        if len(parse_rows) > 10_000:
            raise LiveEvidenceValidationError("GATE_B_AUDIT_BOUND_EXCEEDED")
        parser_versions = tuple(str(row[0]) for row in parse_rows)
        sanitizer_versions = tuple(str(row[1]) for row in parse_rows)

    first_artifact = artifact_views[0] if artifact_views else None
    return GateBAuditView(
        grant_id=authorization_id,
        grant_checksum=str(grant["canonical_checksum"]),
        grant_state=grant_state,
        approval_id=UUID(str(approval["id"])) if approval else None,
        approval_state=str(approval["state"]) if approval else None,
        approval_expires_at=_optional_utc(approval.get("expires_at")) if approval else None,
        authorization_id=authorization_id,
        candidate=candidate,
        provider=provider,
        plan_id=UUID(str(plan["id"])),
        plan_checksum=str(plan["plan_checksum"]),
        resources=resources,
        sync_run_id=sync_run_id,
        sync_run_status=_optional_str(run.get("status")),
        consumed_requests=len(consumptions),
        consumed_attempts=len(attempts),
        consumed_retries=sum(item.attempt_kind == "RETRY" for item in attempt_views),
        consumed_bytes=sum(_optional_int(item.get("actual_bytes")) or 0 for item in consumptions),
        started_at=_optional_utc(run.get("started_at")),
        completed_at=_optional_utc(run.get("completed_at")),
        attempts=attempt_views,
        consumptions=consumption_views,
        artifacts=artifact_views,
        manifests=manifest_views,
        document_version_id=document_version_id,
        document_checksum=document_checksum,
        citation_ids=citation_ids,
        citation_parser_versions=parser_versions,
        citation_sanitizer_versions=sanitizer_versions,
        data_quality_issues=issue_views,
        terminal_validation_id=_summary_uuid(terminal_summary, "terminal_validation_id"),
        terminal_status=(
            _optional_str(terminal_summary.get("status"))
            or (_optional_str(terminal["decision_code"]) if terminal else None)
        ),
        terminal_stage=_optional_str(terminal_summary.get("terminal_stage")),
        warning_codes=_string_tuple(terminal_summary.get("warning_codes")),
        stop_reason=_optional_str(terminal_summary.get("stop_reason")),
        failed_ordinal=_optional_int(terminal_summary.get("failed_ordinal")),
        failed_slice_id=_optional_str(terminal_summary.get("failed_slice_id")),
        artifact_id=first_artifact.artifact_id if first_artifact else None,
        content_checksum=first_artifact.source_checksum if first_artifact else None,
        retrieved_at=first_artifact.acquired_at if first_artifact else None,
        request_attempt_id=first_artifact.request_attempt_id if first_artifact else None,
    )


class SqlAlchemyGateBAuditRepository:
    """Read the committed operational projection for one bounded Gate B Sync Run."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        sync_run_id: UUID,
    ) -> None:
        self._session_factory = session_factory
        self._sync_run_id = sync_run_id

    def get(self) -> GateBAuditView | None:
        with self._session_factory() as session:
            return get_gate_b_audit_view(session, self._sync_run_id)


def _table_exists(session: Session, table_name: str) -> bool:
    return bool(
        session.scalar(
            text("SELECT to_regclass(:table_name) IS NOT NULL"), {"table_name": table_name}
        )
    )


def _bounded_payloads(
    session: Session,
    statement: str,
    parameters: dict[str, object],
    *,
    maximum: int,
) -> list[dict[str, object]]:
    payloads = list(session.scalars(text(statement), parameters).all())
    if len(payloads) > maximum or any(not isinstance(payload, dict) for payload in payloads):
        raise LiveEvidenceValidationError("GATE_B_AUDIT_BOUND_EXCEEDED")
    return payloads


def _audit_resources(
    slices: object, attempts: list[dict[str, object]]
) -> tuple[GateBAuditResourceView, ...]:
    if isinstance(slices, list):
        return tuple(
            GateBAuditResourceView(
                ordinal=index,
                slice_id=str(item.get("slice_id") or item.get("resource_id")),
                endpoint_id=_optional_str(item.get("endpoint_id")),
            )
            for index, item in enumerate(slices)
            if isinstance(item, dict)
        )
    unique: dict[str, str] = {}
    for attempt in attempts:
        unique.setdefault(str(attempt["slice_id"]), str(attempt["endpoint_id"]))
    return tuple(
        GateBAuditResourceView(ordinal=index, slice_id=slice_id, endpoint_id=endpoint_id)
        for index, (slice_id, endpoint_id) in enumerate(unique.items())
    )


def _audit_attempt(
    attempt: dict[str, object],
    consumptions: list[dict[str, object]],
    *,
    is_retry: bool,
) -> GateBAuditAttemptView:
    attempt_id = UUID(str(attempt["id"]))
    consumption = next(
        (item for item in consumptions if UUID(str(item["request_attempt_id"])) == attempt_id),
        None,
    )
    attempt_number = _required_int(attempt["attempt_number"])
    return GateBAuditAttemptView(
        request_attempt_id=attempt_id,
        slice_id=str(attempt["slice_id"]),
        endpoint_id=str(attempt["endpoint_id"]),
        attempt_kind="RETRY" if is_retry else "INITIAL",
        attempt_number=attempt_number,
        retry_number=1 if is_retry else 0,
        started_at=_required_utc(attempt["started_at"]),
        completed_at=_optional_utc(attempt.get("completed_at")),
        status=str(attempt["status"]),
        http_status=_optional_int(attempt.get("response_status_code")),
        response_bytes=_optional_int(attempt.get("response_bytes")) or 0,
        safe_error_code=_optional_str(attempt.get("safe_error_code")),
        socket_opened=_optional_bool(consumption.get("socket_opened")) if consumption else None,
    )


def _audit_consumption(item: dict[str, object]) -> GateBAuditConsumptionView:
    return GateBAuditConsumptionView(
        consumption_id=UUID(str(item["id"])),
        request_attempt_id=UUID(str(item["request_attempt_id"])),
        reserved_bytes=_required_int(item["reserved_bytes"]),
        actual_bytes=_optional_int(item.get("actual_bytes")),
        socket_opened=_optional_bool(item.get("socket_opened")),
        state=str(item["state"]),
        reserved_at=_required_utc(item["reserved_at"]),
        settled_at=_optional_utc(item.get("settled_at")),
    )


def _audit_artifact(item: dict[str, object]) -> GateBAuditArtifactView:
    return GateBAuditArtifactView(
        artifact_id=UUID(str(item["id"])),
        request_attempt_id=UUID(str(item["request_attempt_id"])),
        source_identity=_optional_str(item.get("source_identity")),
        source_checksum=str(item["source_checksum"]),
        content_type=_optional_str(item.get("content_type")),
        byte_count=_optional_int(item.get("byte_count")),
        blob_key=_optional_str(item.get("blob_key")),
        acquired_at=_required_utc(item["acquired_at"]),
        source_published_at=_optional_utc(item.get("source_published_at")),
        synthetic_status=_optional_str(item.get("synthetic_status")),
        license_policy_id=(
            UUID(str(item["license_policy_id"])) if item.get("license_policy_id") else None
        ),
    )


def _audit_manifest(item: dict[str, object]) -> GateBAuditManifestView:
    return GateBAuditManifestView(
        manifest_id=UUID(str(item["id"])),
        artifact_id=UUID(str(item["raw_artifact_id"])),
        batch_checksum=str(item["batch_checksum"]),
        manifest_checksum=str(item["manifest_checksum"]),
        adapter_version=str(item["adapter_version"]),
        parser_version=str(item["parser_version"]),
        schema_version=str(item["schema_version"]),
        record_count=_required_int(item["record_count"]),
        warning_codes=_string_tuple(item.get("warning_codes")),
    )


def _audit_issue(item: dict[str, object]) -> GateBAuditDataQualityIssueView:
    return GateBAuditDataQualityIssueView(
        issue_id=UUID(str(item["id"])),
        manifest_id=UUID(str(item["manifest_id"])),
        rule_code=str(item["rule_code"]),
        severity=str(item["severity"]),
        status=str(item["status"]),
        safe_detail=str(item["safe_detail"]),
    )


def _summary_uuid(summary: dict[str, object], key: str) -> UUID | None:
    value = summary.get(key)
    return UUID(str(value)) if value is not None else None


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _required_int(value: object) -> int:
    if not isinstance(value, int):
        raise LiveEvidenceValidationError("GATE_B_AUDIT_FIELD_INVALID")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _required_int(value)


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise LiveEvidenceValidationError("GATE_B_AUDIT_FIELD_INVALID")
    return value


def _required_utc(value: object) -> datetime:
    if not isinstance(value, (datetime, str)):
        raise LiveEvidenceValidationError("GATE_B_AUDIT_FIELD_INVALID")
    return _utc(value)


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise LiveEvidenceValidationError("GATE_B_AUDIT_FIELD_INVALID")
    return tuple(str(item) for item in value)


def _optional_utc(value: object) -> datetime | None:
    return _utc(value) if isinstance(value, (datetime, str)) else None


def settle_consumption(
    session: Session,
    settlement: ConsumptionSettlementRequest,
) -> LiveAuthorizationConsumptionRecord:
    """Settle actual bytes while holding the same authorization budget lock."""
    byte_limit = session.scalar(
        text(
            "SELECT byte_limit FROM live_authorization_grants "
            "WHERE id = :authorization_id FOR UPDATE"
        ),
        {"authorization_id": settlement.authorization_id},
    )
    if byte_limit is None:
        raise LiveEvidenceValidationError("AUTH_RESERVATION_INVALID")

    row = (
        session.execute(
            text(
                "SELECT id, authorization_id, request_attempt_id, reserved_bytes, "
                "actual_bytes, socket_opened, state, reserved_at, settled_at "
                "FROM live_authorization_consumptions "
                "WHERE authorization_id = :authorization_id "
                "AND request_attempt_id = :request_attempt_id FOR UPDATE"
            ),
            {
                "authorization_id": settlement.authorization_id,
                "request_attempt_id": settlement.request_attempt_id,
            },
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise LiveEvidenceValidationError("AUTH_RESERVATION_INVALID")

    if row["state"] != ConsumptionState.RESERVED.value:
        if (
            row["actual_bytes"] == settlement.actual_bytes
            and row["socket_opened"] is settlement.socket_opened
            and row["state"] == settlement.state.value
            and _utc(row["settled_at"]) == settlement.settled_at
        ):
            return _consumption_record(row)
        raise LiveEvidenceValidationError("AUTH_SETTLEMENT_CONFLICT")

    consumed_bytes = session.scalar(
        text(
            "SELECT coalesce(sum(actual_bytes), 0) "
            "FROM live_authorization_consumptions "
            "WHERE authorization_id = :authorization_id AND state = 'SETTLED'"
        ),
        {"authorization_id": settlement.authorization_id},
    )
    if consumed_bytes is None or consumed_bytes + settlement.actual_bytes > byte_limit:
        raise LiveEvidenceValidationError("AUTH_BYTE_BUDGET_EXCEEDED")

    reservation = ConsumptionReservation(
        id=row["id"],
        authorization_id=row["authorization_id"],
        request_attempt_id=row["request_attempt_id"],
        reserved_bytes=row["reserved_bytes"],
        reserved_at=_utc(row["reserved_at"]),
        state=ConsumptionState.RESERVED,
    )
    record = AuthorizationConsumption.settle(reservation, settlement)
    session.execute(
        text(
            "UPDATE live_authorization_consumptions SET actual_bytes = :actual_bytes, "
            "socket_opened = :socket_opened, state = :state, settled_at = :settled_at "
            "WHERE id = :id"
        ),
        {
            "id": record.id,
            "actual_bytes": record.actual_bytes,
            "socket_opened": record.socket_opened,
            "state": record.state.value,
            "settled_at": record.settled_at,
        },
    )
    return record


def _consumption_record(mapping: RowMapping) -> LiveAuthorizationConsumptionRecord:
    return LiveAuthorizationConsumptionRecord(
        id=mapping["id"],
        authorization_id=mapping["authorization_id"],
        request_attempt_id=mapping["request_attempt_id"],
        reserved_bytes=mapping["reserved_bytes"],
        actual_bytes=mapping["actual_bytes"],
        socket_opened=mapping["socket_opened"],
        state=ConsumptionState(mapping["state"]),
        reserved_at=_utc(mapping["reserved_at"]),
        settled_at=_utc(mapping["settled_at"]),
    )


def consume_authorization(
    session: Session,
    authorization_id: UUID,
) -> LiveAuthorizationState:
    """Append the single terminal CONSUME event under the grant row lock."""
    locked_id = session.scalar(
        text("SELECT id FROM live_authorization_grants WHERE id = :authorization_id FOR UPDATE"),
        {"authorization_id": authorization_id},
    )
    if locked_id is None:
        raise LiveEvidenceValidationError("AUTH_RESERVATION_INVALID")
    event_values = session.scalars(
        text(
            "SELECT event_type FROM live_authorization_events "
            "WHERE authorization_id = :authorization_id ORDER BY sequence"
        ),
        {"authorization_id": authorization_id},
    ).all()
    events = tuple(LiveAuthorizationEventType(value) for value in event_values)
    state = AuthorizationStateMachine.replay(events)
    if state is LiveAuthorizationState.CONSUMED:
        raise LiveEvidenceValidationError("AUTHORIZATION_ALREADY_CONSUMED")
    if state is not LiveAuthorizationState.ACTIVE:
        raise LiveEvidenceValidationError("AUTH_RESERVATION_INVALID")
    sequence = len(events) + 1
    session.execute(
        text(
            "INSERT INTO live_authorization_events "
            "(id, authorization_id, sequence, event_type) "
            "VALUES (:id, :authorization_id, :sequence, 'CONSUME')"
        ),
        {
            "id": uuid4(),
            "authorization_id": authorization_id,
            "sequence": sequence,
        },
    )
    return AuthorizationStateMachine.transition(
        state,
        LiveAuthorizationEventType.CONSUME,
    )
