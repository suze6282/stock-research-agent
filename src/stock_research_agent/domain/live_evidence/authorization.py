from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import uuid4

from stock_research_agent.domain.live_evidence.enums import (
    ConsumptionState,
    LiveAuthorizationEventType,
    LiveAuthorizationState,
)
from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.schemas import (
    AuthorizationDecision,
    AuthorizationExecutionScope,
    AuthorizationRevocationResult,
    ConsumptionReservation,
    ConsumptionReservationRequest,
    ConsumptionSettlementRequest,
    LiveAuthorizationConsumptionRecord,
    LiveAuthorizationGrantWrite,
    RevokeAuthorizationRequest,
)

_TERMINAL_STATES = frozenset(
    {
        LiveAuthorizationState.CONSUMED,
        LiveAuthorizationState.EXPIRED,
        LiveAuthorizationState.REVOKED,
        LiveAuthorizationState.CANCELLED,
    }
)
_TRANSITIONS = {
    (LiveAuthorizationState.DRAFT, LiveAuthorizationEventType.APPROVE): (
        LiveAuthorizationState.APPROVED
    ),
    (LiveAuthorizationState.DRAFT, LiveAuthorizationEventType.CANCEL): (
        LiveAuthorizationState.CANCELLED
    ),
    (LiveAuthorizationState.DRAFT, LiveAuthorizationEventType.EXPIRE): (
        LiveAuthorizationState.EXPIRED
    ),
    (LiveAuthorizationState.APPROVED, LiveAuthorizationEventType.ACTIVATE): (
        LiveAuthorizationState.ACTIVE
    ),
    (LiveAuthorizationState.APPROVED, LiveAuthorizationEventType.CANCEL): (
        LiveAuthorizationState.CANCELLED
    ),
    (LiveAuthorizationState.APPROVED, LiveAuthorizationEventType.EXPIRE): (
        LiveAuthorizationState.EXPIRED
    ),
    (LiveAuthorizationState.APPROVED, LiveAuthorizationEventType.REVOKE): (
        LiveAuthorizationState.REVOKED
    ),
    (LiveAuthorizationState.ACTIVE, LiveAuthorizationEventType.CONSUME): (
        LiveAuthorizationState.CONSUMED
    ),
    (LiveAuthorizationState.ACTIVE, LiveAuthorizationEventType.EXPIRE): (
        LiveAuthorizationState.EXPIRED
    ),
    (LiveAuthorizationState.ACTIVE, LiveAuthorizationEventType.REVOKE): (
        LiveAuthorizationState.REVOKED
    ),
}


class AuthorizationStateMachine:
    @staticmethod
    def transition(
        current: LiveAuthorizationState,
        event: LiveAuthorizationEventType,
    ) -> LiveAuthorizationState:
        if current in _TERMINAL_STATES:
            raise LiveEvidenceValidationError("AUTH_TERMINAL_IMMUTABLE")
        next_state = _TRANSITIONS.get((current, event))
        if next_state is None:
            raise LiveEvidenceValidationError("AUTH_TRANSITION_INVALID")
        return next_state

    @classmethod
    def replay(
        cls,
        events: Iterable[LiveAuthorizationEventType],
    ) -> LiveAuthorizationState:
        state = LiveAuthorizationState.DRAFT
        for event in events:
            state = cls.transition(state, event)
        return state


class AuthorizationConsumption:
    @staticmethod
    def reserve(
        request: ConsumptionReservationRequest,
        *,
        existing: ConsumptionReservation | None = None,
    ) -> ConsumptionReservation:
        if existing is not None:
            if (
                existing.authorization_id == request.authorization_id
                and existing.request_attempt_id == request.request_attempt_id
                and existing.reserved_bytes == request.reserved_bytes
                and existing.reserved_at == request.reserved_at
            ):
                return existing
            raise LiveEvidenceValidationError("AUTH_CONSUMPTION_DUPLICATE")
        return ConsumptionReservation(
            id=uuid4(),
            **request.model_dump(),
            state=ConsumptionState.RESERVED,
        )

    @staticmethod
    def settle(
        reservation: ConsumptionReservation,
        settlement: ConsumptionSettlementRequest,
    ) -> LiveAuthorizationConsumptionRecord:
        identity_matches = (
            reservation.authorization_id == settlement.authorization_id
            and reservation.request_attempt_id == settlement.request_attempt_id
        )
        valid_accounting = (
            settlement.actual_bytes <= reservation.reserved_bytes
            and settlement.settled_at >= reservation.reserved_at
        )
        valid_abandonment = settlement.state is not ConsumptionState.ABANDONED or (
            not settlement.socket_opened and settlement.actual_bytes == 0
        )
        valid_settlement = (
            settlement.state is not ConsumptionState.SETTLED or settlement.socket_opened
        )
        if not all((identity_matches, valid_accounting, valid_abandonment, valid_settlement)):
            raise LiveEvidenceValidationError("AUTH_RESERVATION_INVALID")
        return LiveAuthorizationConsumptionRecord(
            id=reservation.id,
            authorization_id=reservation.authorization_id,
            request_attempt_id=reservation.request_attempt_id,
            reserved_bytes=reservation.reserved_bytes,
            actual_bytes=settlement.actual_bytes,
            socket_opened=settlement.socket_opened,
            state=settlement.state,
            reserved_at=reservation.reserved_at,
            settled_at=settlement.settled_at,
        )


def derive_state(
    grant: LiveAuthorizationGrantWrite,
    events: Iterable[LiveAuthorizationEventType],
    now: datetime,
) -> LiveAuthorizationState:
    if now.tzinfo is None or now.utcoffset() is None:
        raise LiveEvidenceValidationError("AUTH_SCOPE_INVALID")
    current = AuthorizationStateMachine.replay(events)
    if current in _TERMINAL_STATES:
        return current
    if now.astimezone(UTC) >= grant.expires_at:
        return LiveAuthorizationState.EXPIRED
    return current


def require_active_authorization(
    grant: LiveAuthorizationGrantWrite,
    events: Iterable[LiveAuthorizationEventType],
    now: datetime,
) -> LiveAuthorizationState:
    state = derive_state(grant, events, now)
    if state is LiveAuthorizationState.EXPIRED:
        raise LiveEvidenceValidationError("AUTHORIZATION_EXPIRED")
    if state is LiveAuthorizationState.REVOKED:
        raise LiveEvidenceValidationError("AUTHORIZATION_REVOKED")
    if state is not LiveAuthorizationState.ACTIVE:
        raise LiveEvidenceValidationError("AUTH_RESERVATION_INVALID")
    return state


def revoke_authorization(
    request: RevokeAuthorizationRequest,
    events: Iterable[LiveAuthorizationEventType],
) -> AuthorizationRevocationResult:
    history = tuple(events)
    if len(history) != request.expected_event_count:
        raise LiveEvidenceValidationError("AUTH_REVOCATION_CONFLICT")
    current = AuthorizationStateMachine.replay(history)
    if current != request.expected_state or current in _TERMINAL_STATES:
        raise LiveEvidenceValidationError("AUTH_REVOCATION_CONFLICT")
    try:
        state = AuthorizationStateMachine.transition(
            current,
            LiveAuthorizationEventType.REVOKE,
        )
    except LiveEvidenceValidationError as error:
        raise LiveEvidenceValidationError("AUTH_REVOCATION_CONFLICT") from error
    return AuthorizationRevocationResult(
        authorization_id=request.authorization_id,
        state=state,
        events=(*history, LiveAuthorizationEventType.REVOKE),
        event_sequence=len(history) + 1,
    )


def validate_execution_scope(
    grant: LiveAuthorizationGrantWrite,
    scope: AuthorizationExecutionScope,
) -> AuthorizationDecision:
    provider_scope = (
        grant.provider_definition_id,
        grant.provider_code,
        grant.provider_definition_version,
    )
    requested_provider_scope = (
        scope.provider_definition_id,
        scope.provider_code,
        scope.provider_definition_version,
    )
    if provider_scope != requested_provider_scope:
        raise LiveEvidenceValidationError("AUTH_PROVIDER_MISMATCH")
    capability_scope = (
        grant.provider_capability_id,
        grant.capability_code,
        grant.capability_version,
    )
    requested_capability_scope = (
        scope.provider_capability_id,
        scope.capability_code,
        scope.capability_version,
    )
    if capability_scope != requested_capability_scope:
        raise LiveEvidenceValidationError("AUTH_CAPABILITY_MISMATCH")
    if (grant.security_id, grant.issuer_id) != (scope.security_id, scope.issuer_id):
        raise LiveEvidenceValidationError("AUTH_SECURITY_MISMATCH")
    if grant.provider_security_identifier != scope.provider_security_identifier:
        raise LiveEvidenceValidationError("AUTH_PROVIDER_IDENTIFIER_MISMATCH")
    return AuthorizationDecision(allowed=True, failure_code=None)
