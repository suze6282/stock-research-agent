"""Authorization- and permit-gated SEC Gate B transport controller."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizedGateBExecution,
)
from stock_research_agent.domain.providers.credentials import CredentialReferenceRecord
from stock_research_agent.domain.providers.schemas import FrozenProviderContract
from stock_research_agent.domain.providers.sync import ProviderSyncPlanRecord
from stock_research_agent.providers.credentials import (
    EnvironmentCredentialResolver,
    ProtectedRequestIdentity,
)
from stock_research_agent.providers.errors import (
    HttpTimeoutError,
    ProviderHttpError,
    RetryExhaustedError,
)
from stock_research_agent.providers.http_client import HttpRequest, HttpResult, SafeHttpClient
from stock_research_agent.providers.retry import ProviderRetryOutcome, RetryDecision
from stock_research_agent.providers.sec_edgar.policy import (
    SecAuthorizedResource,
    bind_sec_authorized_plan,
)
from stock_research_agent.providers.sec_edgar.request_identity import (
    resolve_sec_request_identity,
)
from stock_research_agent.providers.sec_edgar.retry import (
    SecAttemptKind,
    SecAttemptPermit,
    SecAttemptReservationPort,
    SecAttemptReservationRequest,
)


class SecRetryControllerPort(Protocol):
    def classify(
        self,
        outcome: ProviderRetryOutcome,
        *,
        execution: AuthorizedGateBExecution,
        resource: SecAuthorizedResource,
        previous_attempt: SecAttemptPermit,
        reservations: SecAttemptReservationPort,
    ) -> RetryDecision | SecAttemptPermit: ...


class SecTransportStatus(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class SecPhysicalAttempt(FrozenProviderContract):
    permit: SecAttemptPermit
    response: HttpResult | None
    safe_error_code: str | None = None
    started_at: datetime
    completed_at: datetime
    socket_opened: bool | None


class SecTransportResult(FrozenProviderContract):
    status: SecTransportStatus
    reason_code: str
    attempts: tuple[SecPhysicalAttempt, ...]


HttpClientFactory = Callable[[ProtectedRequestIdentity], SafeHttpClient]


class SecGateBTransportController:
    """Execute only canonical authorized SEC resources with committed permits."""

    def __init__(
        self,
        *,
        credential_resolver: EnvironmentCredentialResolver,
        reservations: SecAttemptReservationPort,
        retry_controller: SecRetryControllerPort,
        http_client_factory: HttpClientFactory,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._credential_resolver = credential_resolver
        self._reservations = reservations
        self._retry_controller = retry_controller
        self._http_client_factory = http_client_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self,
        execution: AuthorizedGateBExecution,
        *,
        plan: ProviderSyncPlanRecord,
        slice_id: str,
        contact_reference: CredentialReferenceRecord,
        permit: SecAttemptPermit | None = None,
    ) -> SecTransportResult:
        authorized_plan = bind_sec_authorized_plan(execution, plan)
        resource = authorized_plan.require_resource(slice_id)
        if permit is None:
            permit = self._reservations.reserve(
                SecAttemptReservationRequest(
                    authorization_id=execution.authorization_id,
                    plan_id=execution.plan_id,
                    plan_checksum=execution.plan_checksum,
                    slice_id=resource.slice_id,
                    endpoint_id=resource.request.endpoint_id,
                    attempt_number=1,
                    kind=SecAttemptKind.INITIAL,
                )
            )
        self._require_matching_permit(
            execution,
            resource,
            permit,
            attempt_number=permit.attempt_number,
            kind=SecAttemptKind.INITIAL,
        )
        try:
            identity = resolve_sec_request_identity(
                execution,
                contact_reference,
                self._credential_resolver,
            )
        except ValueError:
            occurred_at = self._clock()
            attempt = SecPhysicalAttempt(
                permit=permit,
                response=None,
                safe_error_code="SEC_CONTACT_RESOLUTION_FAILED",
                started_at=occurred_at,
                completed_at=occurred_at,
                socket_opened=False,
            )
            return SecTransportResult(
                status=SecTransportStatus.BLOCKED,
                reason_code="SEC_CONTACT_RESOLUTION_FAILED",
                attempts=(attempt,),
            )
        attempt = self._send(resource, permit, identity)
        if attempt.response is not None and 200 <= attempt.response.status_code < 300:
            return SecTransportResult(
                status=SecTransportStatus.COMPLETED,
                reason_code="SEC_TRANSPORT_COMPLETED",
                attempts=(attempt,),
            )
        outcome = ProviderRetryOutcome(
            http_status=(attempt.response.status_code if attempt.response is not None else None),
            error_code=attempt.safe_error_code,
        )
        decision = self._retry_controller.classify(
            outcome,
            execution=execution,
            resource=resource,
            previous_attempt=permit,
            reservations=self._reservations,
        )
        if isinstance(decision, SecAttemptPermit):
            self._require_matching_permit(
                execution,
                resource,
                decision,
                attempt_number=permit.attempt_number + 1,
                kind=SecAttemptKind.RETRY,
            )
            retry_attempt = self._send(resource, decision, identity)
            if (
                retry_attempt.response is not None
                and 200 <= retry_attempt.response.status_code < 300
            ):
                return SecTransportResult(
                    status=SecTransportStatus.COMPLETED,
                    reason_code="SEC_TRANSPORT_COMPLETED",
                    attempts=(attempt, retry_attempt),
                )
            reason_code = (
                "SEC_HTTP_429_ABORT"
                if retry_attempt.response is not None and retry_attempt.response.status_code == 429
                else "SEC_TRANSIENT_RETRY_EXHAUSTED"
            )
            return SecTransportResult(
                status=SecTransportStatus.BLOCKED,
                reason_code=reason_code,
                attempts=(attempt, retry_attempt),
            )
        return SecTransportResult(
            status=SecTransportStatus.BLOCKED,
            reason_code=decision.reason_code,
            attempts=(attempt,),
        )

    def _send(
        self,
        resource: SecAuthorizedResource,
        permit: SecAttemptPermit,
        identity: ProtectedRequestIdentity,
    ) -> SecPhysicalAttempt:
        started_at = self._clock()
        try:
            with self._http_client_factory(identity) as client:
                response = client.get(
                    HttpRequest(
                        url=resource.request.url,
                        accept=resource.request.accepted_content_types[0],
                        request_id=str(permit.request_attempt_id),
                        provider_request_id=resource.slice_id,
                    )
                )
        except HttpTimeoutError:
            return SecPhysicalAttempt(
                permit=permit,
                response=None,
                safe_error_code="READ_TIMEOUT",
                started_at=started_at,
                completed_at=self._clock(),
                socket_opened=None,
            )
        except RetryExhaustedError:
            return SecPhysicalAttempt(
                permit=permit,
                response=None,
                safe_error_code="CONNECT_TIMEOUT",
                started_at=started_at,
                completed_at=self._clock(),
                socket_opened=None,
            )
        except ProviderHttpError:
            return SecPhysicalAttempt(
                permit=permit,
                response=None,
                safe_error_code="SEC_TRANSPORT_BLOCKED",
                started_at=started_at,
                completed_at=self._clock(),
                socket_opened=None,
            )
        return SecPhysicalAttempt(
            permit=permit,
            response=response,
            started_at=started_at,
            completed_at=self._clock(),
            socket_opened=True,
        )

    @staticmethod
    def _require_matching_permit(
        execution: AuthorizedGateBExecution,
        resource: SecAuthorizedResource,
        permit: SecAttemptPermit,
        *,
        attempt_number: int,
        kind: SecAttemptKind,
    ) -> None:
        if (
            permit.authorization_id != execution.authorization_id
            or permit.plan_id != execution.plan_id
            or permit.plan_checksum != execution.plan_checksum
            or permit.slice_id != resource.slice_id
            or permit.endpoint_id != resource.request.endpoint_id
            or permit.attempt_number != attempt_number
            or permit.kind is not kind
        ):
            raise ValueError("SEC_ATTEMPT_RESERVATION_REQUIRED")
