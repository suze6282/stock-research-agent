from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from stock_research_agent.domain.providers.authorization import (
    LiveAuthorization,
    LiveAuthorizationExecutionScope,
    LiveAuthorizationGate,
)
from stock_research_agent.domain.providers.enums import ProviderLiveAuthorizationStatus

NOW = datetime(2026, 7, 29, tzinfo=UTC)


def _scope() -> LiveAuthorizationExecutionScope:
    return LiveAuthorizationExecutionScope(
        provider_definition_id=uuid4(),
        provider_capability_id=uuid4(),
        host="data.example.com",
        path="/v1/filings",
        requested_requests=1,
        requested_bytes=1024,
        validation_run_id=uuid4(),
        required_approval_phrase_checksum="a" * 64,
    )


def _authorization(scope: LiveAuthorizationExecutionScope) -> LiveAuthorization:
    return LiveAuthorization(
        authorization_id=uuid4(),
        provider_definition_id=scope.provider_definition_id,
        provider_capability_id=scope.provider_capability_id,
        allowed_hosts=(scope.host,),
        allowed_paths=(scope.path,),
        max_requests=1,
        max_bytes=1024,
        expires_at=NOW + timedelta(minutes=5),
        actor_id="LOCAL_OPERATOR",
        approval_phrase_checksum=scope.required_approval_phrase_checksum,
        validation_run_id=scope.validation_run_id,
        consumed=False,
    )


def test_exact_finite_live_authorization_is_authorized_without_network() -> None:
    scope = _scope()
    decision = LiveAuthorizationGate.evaluate(_authorization(scope), scope, NOW)

    assert decision.allowed is True
    assert decision.status is ProviderLiveAuthorizationStatus.AUTHORIZED
    assert decision.reason_code == "LIVE_AUTHORIZATION_EXACT_MATCH"


def test_absent_authorization_is_blocked_and_not_attempted() -> None:
    decision = LiveAuthorizationGate.evaluate(None, _scope(), NOW)

    assert decision.allowed is False
    assert decision.status is ProviderLiveAuthorizationStatus.NOT_ATTEMPTED
    assert decision.reason_code == "LIVE_AUTHORIZATION_REQUIRED"


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"provider_definition_id": uuid4()}, "LIVE_AUTHORIZATION_PROVIDER_MISMATCH"),
        ({"provider_capability_id": uuid4()}, "LIVE_AUTHORIZATION_CAPABILITY_MISMATCH"),
        ({"allowed_hosts": ("other.example.com",)}, "LIVE_AUTHORIZATION_HOST_DENIED"),
        ({"allowed_paths": ("/v1/other",)}, "LIVE_AUTHORIZATION_PATH_DENIED"),
        ({"max_requests": 1}, "LIVE_AUTHORIZATION_REQUEST_BUDGET_EXCEEDED"),
        ({"max_bytes": 1023}, "LIVE_AUTHORIZATION_BYTE_BUDGET_EXCEEDED"),
        ({"expires_at": NOW}, "LIVE_AUTHORIZATION_EXPIRED"),
        ({"consumed": True}, "LIVE_AUTHORIZATION_REPLAYED"),
        ({"validation_run_id": uuid4()}, "LIVE_AUTHORIZATION_RUN_MISMATCH"),
        ({"approval_phrase_checksum": "b" * 64}, "LIVE_AUTHORIZATION_PHRASE_MISMATCH"),
    ],
)
def test_wrong_expired_replayed_or_widened_authorization_is_blocked(
    updates: dict[str, object],
    reason: str,
) -> None:
    scope = _scope()
    if reason == "LIVE_AUTHORIZATION_REQUEST_BUDGET_EXCEEDED":
        scope = scope.model_copy(update={"requested_requests": 2})
    authorization = _authorization(scope).model_copy(update=updates)

    decision = LiveAuthorizationGate.evaluate(authorization, scope, NOW)

    assert decision.allowed is False
    assert decision.reason_code == reason
