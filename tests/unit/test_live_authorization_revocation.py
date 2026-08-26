from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from stock_research_agent.domain.live_evidence.authorization import (
    require_active_authorization,
    revoke_authorization,
)
from stock_research_agent.domain.live_evidence.enums import (
    LiveAuthorizationEventType,
    LiveAuthorizationState,
)
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.schemas import (
    LiveAuthorizationGrantWrite,
    RevokeAuthorizationRequest,
)


def _request(expected: LiveAuthorizationState) -> RevokeAuthorizationRequest:
    return RevokeAuthorizationRequest(
        authorization_id=uuid4(),
        expected_state=expected,
        expected_event_count=2,
        reason_code="OPERATOR_REVOKED",
        revoked_by="LOCAL_OPERATOR",
        revoked_at=datetime(2026, 8, 1, 5, 0, tzinfo=UTC),
    )


def test_revoke_appends_event_without_rewriting_history() -> None:
    original = (
        LiveAuthorizationEventType.APPROVE,
        LiveAuthorizationEventType.ACTIVATE,
    )

    result = revoke_authorization(_request(LiveAuthorizationState.ACTIVE), original)

    assert original == (
        LiveAuthorizationEventType.APPROVE,
        LiveAuthorizationEventType.ACTIVATE,
    )
    assert result.events == (*original, LiveAuthorizationEventType.REVOKE)
    assert result.state is LiveAuthorizationState.REVOKED
    assert result.event_sequence == 3


@pytest.mark.parametrize(
    "events",
    [
        (
            LiveAuthorizationEventType.APPROVE,
            LiveAuthorizationEventType.ACTIVATE,
            LiveAuthorizationEventType.REVOKE,
        ),
        (
            LiveAuthorizationEventType.APPROVE,
            LiveAuthorizationEventType.ACTIVATE,
            LiveAuthorizationEventType.CONSUME,
        ),
    ],
)
def test_terminal_or_duplicate_revocation_is_a_conflict(
    events: tuple[LiveAuthorizationEventType, ...],
) -> None:
    request = _request(LiveAuthorizationState.ACTIVE).model_copy(
        update={"expected_event_count": len(events)}
    )

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        revoke_authorization(request, events)

    assert exc_info.value.code == "AUTH_REVOCATION_CONFLICT"


def test_stale_event_count_cannot_revoke_a_changed_grant() -> None:
    events = (
        LiveAuthorizationEventType.APPROVE,
        LiveAuthorizationEventType.ACTIVATE,
    )
    request = _request(LiveAuthorizationState.ACTIVE).model_copy(update={"expected_event_count": 1})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        revoke_authorization(request, events)

    assert exc_info.value.code == "AUTH_REVOCATION_CONFLICT"


def test_revoked_grant_is_rejected_with_specific_code() -> None:
    now = datetime(2026, 8, 1, 5, 0, tzinfo=UTC)
    grant = LiveAuthorizationGrantWrite.model_construct(expires_at=now + timedelta(minutes=1))
    events = (
        LiveAuthorizationEventType.APPROVE,
        LiveAuthorizationEventType.ACTIVATE,
        LiveAuthorizationEventType.REVOKE,
    )

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        require_active_authorization(grant, events, now)

    assert exc_info.value.code == "AUTHORIZATION_REVOKED"
