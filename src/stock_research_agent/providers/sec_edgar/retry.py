"""SEC Gate B attempt capabilities and retry-controller boundary."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizedGateBExecution,
)
from stock_research_agent.domain.providers.schemas import Checksum, FrozenProviderContract
from stock_research_agent.providers.retry import ProviderRetryOutcome, RetryDecision
from stock_research_agent.providers.sec_edgar.policy import SecAuthorizedResource

_TRANSIENT_STATUS_CODES = frozenset({500, 502, 503, 504})
_TRANSIENT_ERROR_CODES = frozenset({"CONNECT_TIMEOUT", "READ_TIMEOUT"})


class SecAttemptKind(StrEnum):
    INITIAL = "INITIAL"
    RETRY = "RETRY"


class SecAttemptReservationRequest(FrozenProviderContract):
    authorization_id: UUID
    plan_id: UUID
    plan_checksum: Checksum
    slice_id: str = Field(min_length=1, max_length=64)
    endpoint_id: str = Field(min_length=1, max_length=128)
    attempt_number: int = Field(ge=1, le=4)
    kind: SecAttemptKind


class SecAttemptPermit(SecAttemptReservationRequest):
    request_attempt_id: UUID


class SecExecutionStartResult(FrozenProviderContract):
    execution: AuthorizedGateBExecution
    initial_permit: SecAttemptPermit


class SecAttemptReservationPort(Protocol):
    def reserve(self, request: SecAttemptReservationRequest) -> SecAttemptPermit: ...


class SecGateBRetryController:
    """The sole retry-decision authority for the SEC Gate B pilot."""

    def classify(
        self,
        outcome: ProviderRetryOutcome,
        *,
        execution: AuthorizedGateBExecution,
        resource: SecAuthorizedResource,
        previous_attempt: SecAttemptPermit,
        reservations: SecAttemptReservationPort,
    ) -> RetryDecision | SecAttemptPermit:
        if outcome.http_status == 429:
            return _terminal("SEC_HTTP_429_ABORT")
        eligible = (
            outcome.http_status in _TRANSIENT_STATUS_CODES
            or outcome.error_code in _TRANSIENT_ERROR_CODES
        )
        if not eligible:
            return _terminal("SEC_RETRY_NOT_ELIGIBLE")
        if (
            previous_attempt.authorization_id != execution.authorization_id
            or previous_attempt.plan_id != execution.plan_id
            or previous_attempt.plan_checksum != execution.plan_checksum
            or previous_attempt.slice_id != resource.slice_id
            or previous_attempt.endpoint_id != resource.request.endpoint_id
            or previous_attempt.attempt_number >= 4
        ):
            return _terminal("SEC_ATTEMPT_RESERVATION_REQUIRED")
        request = SecAttemptReservationRequest(
            authorization_id=execution.authorization_id,
            plan_id=execution.plan_id,
            plan_checksum=execution.plan_checksum,
            slice_id=resource.slice_id,
            endpoint_id=resource.request.endpoint_id,
            attempt_number=previous_attempt.attempt_number + 1,
            kind=SecAttemptKind.RETRY,
        )
        try:
            permit = reservations.reserve(request)
        except ValueError:
            return _terminal("SEC_RETRY_BUDGET_EXHAUSTED")
        if (
            permit.authorization_id != request.authorization_id
            or permit.plan_id != request.plan_id
            or permit.plan_checksum != request.plan_checksum
            or permit.slice_id != request.slice_id
            or permit.endpoint_id != request.endpoint_id
            or permit.attempt_number != request.attempt_number
            or permit.kind is not SecAttemptKind.RETRY
        ):
            return _terminal("SEC_ATTEMPT_RESERVATION_REQUIRED")
        return permit


def _terminal(reason_code: str) -> RetryDecision:
    return RetryDecision(
        retry=False,
        reason_code=reason_code,
        next_attempt=None,
        delay_seconds=Decimal(0),
        resolve_credential_again=False,
    )
