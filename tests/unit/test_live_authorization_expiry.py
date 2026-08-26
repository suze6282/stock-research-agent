from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from stock_research_agent.domain.live_evidence.authorization import (
    derive_state,
    require_active_authorization,
)
from stock_research_agent.domain.live_evidence.enums import (
    LiveAuthorizationEventType,
    LiveAuthorizationState,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.schemas import LiveAuthorizationGrantWrite


def _grant(expires_at: datetime) -> LiveAuthorizationGrantWrite:
    return LiveAuthorizationGrantWrite.model_construct(expires_at=expires_at)


def test_active_grant_expires_at_exact_deadline() -> None:
    expires_at = datetime(2026, 8, 1, 4, 0, tzinfo=UTC)
    events = (
        LiveAuthorizationEventType.APPROVE,
        LiveAuthorizationEventType.ACTIVATE,
    )

    assert derive_state(_grant(expires_at), events, expires_at - timedelta(microseconds=1)) is (
        LiveAuthorizationState.ACTIVE
    )
    assert derive_state(_grant(expires_at), events, expires_at) is LiveAuthorizationState.EXPIRED


@pytest.mark.parametrize(
    ("terminal_event", "expected"),
    [
        (LiveAuthorizationEventType.CONSUME, LiveAuthorizationState.CONSUMED),
        (LiveAuthorizationEventType.REVOKE, LiveAuthorizationState.REVOKED),
    ],
)
def test_expiry_does_not_rewrite_an_existing_terminal_state(
    terminal_event: LiveAuthorizationEventType,
    expected: LiveAuthorizationState,
) -> None:
    expires_at = datetime(2026, 8, 1, 4, 0, tzinfo=UTC)
    events = (
        LiveAuthorizationEventType.APPROVE,
        LiveAuthorizationEventType.ACTIVATE,
        terminal_event,
    )

    assert derive_state(_grant(expires_at), events, expires_at) is expected


def test_expired_grant_is_rejected_before_reservation_or_execution() -> None:
    expires_at = datetime(2026, 8, 1, 4, 0, tzinfo=UTC)
    events = (
        LiveAuthorizationEventType.APPROVE,
        LiveAuthorizationEventType.ACTIVATE,
    )

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        require_active_authorization(_grant(expires_at), events, expires_at)

    assert exc_info.value.code == "AUTHORIZATION_EXPIRED"
