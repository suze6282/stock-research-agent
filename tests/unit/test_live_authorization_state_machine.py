from __future__ import annotations

import pytest

from stock_research_agent.domain.live_evidence.authorization import AuthorizationStateMachine
from stock_research_agent.domain.live_evidence.enums import (
    LiveAuthorizationEventType,
    LiveAuthorizationState,
)
from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError


@pytest.mark.parametrize(
    ("current", "event", "expected"),
    [
        (
            LiveAuthorizationState.DRAFT,
            LiveAuthorizationEventType.APPROVE,
            LiveAuthorizationState.APPROVED,
        ),
        (
            LiveAuthorizationState.DRAFT,
            LiveAuthorizationEventType.CANCEL,
            LiveAuthorizationState.CANCELLED,
        ),
        (
            LiveAuthorizationState.DRAFT,
            LiveAuthorizationEventType.EXPIRE,
            LiveAuthorizationState.EXPIRED,
        ),
        (
            LiveAuthorizationState.APPROVED,
            LiveAuthorizationEventType.ACTIVATE,
            LiveAuthorizationState.ACTIVE,
        ),
        (
            LiveAuthorizationState.APPROVED,
            LiveAuthorizationEventType.REVOKE,
            LiveAuthorizationState.REVOKED,
        ),
        (
            LiveAuthorizationState.ACTIVE,
            LiveAuthorizationEventType.CONSUME,
            LiveAuthorizationState.CONSUMED,
        ),
        (
            LiveAuthorizationState.ACTIVE,
            LiveAuthorizationEventType.REVOKE,
            LiveAuthorizationState.REVOKED,
        ),
    ],
)
def test_state_machine_accepts_only_explicit_transitions(
    current: LiveAuthorizationState,
    event: LiveAuthorizationEventType,
    expected: LiveAuthorizationState,
) -> None:
    assert AuthorizationStateMachine.transition(current, event) is expected


@pytest.mark.parametrize(
    "terminal",
    [
        LiveAuthorizationState.CONSUMED,
        LiveAuthorizationState.EXPIRED,
        LiveAuthorizationState.REVOKED,
        LiveAuthorizationState.CANCELLED,
    ],
)
@pytest.mark.parametrize("event", list(LiveAuthorizationEventType))
def test_terminal_state_cannot_transition(
    terminal: LiveAuthorizationState,
    event: LiveAuthorizationEventType,
) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        AuthorizationStateMachine.transition(terminal, event)

    assert exc_info.value.code == "AUTH_TERMINAL_IMMUTABLE"


@pytest.mark.parametrize(
    ("current", "event"),
    [
        (LiveAuthorizationState.DRAFT, LiveAuthorizationEventType.ACTIVATE),
        (LiveAuthorizationState.DRAFT, LiveAuthorizationEventType.CONSUME),
        (LiveAuthorizationState.APPROVED, LiveAuthorizationEventType.APPROVE),
        (LiveAuthorizationState.APPROVED, LiveAuthorizationEventType.CONSUME),
        (LiveAuthorizationState.ACTIVE, LiveAuthorizationEventType.ACTIVATE),
        (LiveAuthorizationState.ACTIVE, LiveAuthorizationEventType.CANCEL),
    ],
)
def test_invalid_transition_has_stable_failure(
    current: LiveAuthorizationState,
    event: LiveAuthorizationEventType,
) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        AuthorizationStateMachine.transition(current, event)

    assert exc_info.value.code == "AUTH_TRANSITION_INVALID"


def test_replay_is_deterministic_and_starts_at_draft() -> None:
    events = (
        LiveAuthorizationEventType.APPROVE,
        LiveAuthorizationEventType.ACTIVATE,
        LiveAuthorizationEventType.CONSUME,
    )

    assert AuthorizationStateMachine.replay(events) is LiveAuthorizationState.CONSUMED
    assert AuthorizationStateMachine.replay(()) is LiveAuthorizationState.DRAFT
