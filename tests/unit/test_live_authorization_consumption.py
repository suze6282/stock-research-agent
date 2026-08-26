from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from stock_research_agent.domain.live_evidence.authorization import (
    AuthorizationConsumption,
)
from stock_research_agent.domain.live_evidence.enums import ConsumptionState
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.schemas import (
    ConsumptionReservationRequest,
    ConsumptionSettlementRequest,
)


def _reservation_request() -> ConsumptionReservationRequest:
    return ConsumptionReservationRequest(
        authorization_id=uuid4(),
        request_attempt_id=uuid4(),
        reserved_bytes=4096,
        reserved_at=datetime(2026, 8, 1, 1, 2, tzinfo=UTC),
    )


def test_consumption_states_are_finite() -> None:
    assert {item.value for item in ConsumptionState} == {
        "RESERVED",
        "SETTLED",
        "ABANDONED",
    }


def test_reservation_is_bound_to_one_authorization_and_attempt() -> None:
    request = _reservation_request()

    reservation = AuthorizationConsumption.reserve(request)

    assert reservation.authorization_id == request.authorization_id
    assert reservation.request_attempt_id == request.request_attempt_id
    assert reservation.reserved_bytes == 4096
    assert reservation.state is ConsumptionState.RESERVED


def test_repeating_identical_request_attempt_is_idempotent() -> None:
    request = _reservation_request()
    existing = AuthorizationConsumption.reserve(request)

    repeated = AuthorizationConsumption.reserve(request, existing=existing)

    assert repeated is existing


def test_reusing_attempt_for_different_reservation_is_rejected() -> None:
    request = _reservation_request()
    existing = AuthorizationConsumption.reserve(request)
    changed = request.model_copy(update={"reserved_bytes": 2048})

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        AuthorizationConsumption.reserve(changed, existing=existing)

    assert exc_info.value.code == "AUTH_CONSUMPTION_DUPLICATE"


def test_settlement_records_actual_received_bytes() -> None:
    reservation = AuthorizationConsumption.reserve(_reservation_request())
    settlement = ConsumptionSettlementRequest(
        authorization_id=reservation.authorization_id,
        request_attempt_id=reservation.request_attempt_id,
        actual_bytes=1536,
        socket_opened=True,
        state=ConsumptionState.SETTLED,
        settled_at=reservation.reserved_at + timedelta(seconds=2),
    )

    record = AuthorizationConsumption.settle(reservation, settlement)

    assert record.reserved_bytes == 4096
    assert record.actual_bytes == 1536
    assert record.socket_opened is True
    assert record.state is ConsumptionState.SETTLED


@pytest.mark.parametrize(
    "change",
    [
        {"authorization_id": uuid4()},
        {"request_attempt_id": uuid4()},
        {"actual_bytes": 4097},
    ],
)
def test_settlement_must_match_reservation(change: dict[str, object]) -> None:
    reservation = AuthorizationConsumption.reserve(_reservation_request())
    settlement = ConsumptionSettlementRequest(
        authorization_id=reservation.authorization_id,
        request_attempt_id=reservation.request_attempt_id,
        actual_bytes=100,
        socket_opened=True,
        state=ConsumptionState.SETTLED,
        settled_at=reservation.reserved_at + timedelta(seconds=1),
    ).model_copy(update=change)

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        AuthorizationConsumption.settle(reservation, settlement)

    assert exc_info.value.code == "AUTH_RESERVATION_INVALID"


def test_unstarted_reservation_can_be_abandoned_without_refund_ambiguity() -> None:
    reservation = AuthorizationConsumption.reserve(_reservation_request())
    settlement = ConsumptionSettlementRequest(
        authorization_id=reservation.authorization_id,
        request_attempt_id=reservation.request_attempt_id,
        actual_bytes=0,
        socket_opened=False,
        state=ConsumptionState.ABANDONED,
        settled_at=reservation.reserved_at + timedelta(seconds=1),
    )

    record = AuthorizationConsumption.settle(reservation, settlement)

    assert record.state is ConsumptionState.ABANDONED
    assert record.actual_bytes == 0


@pytest.mark.parametrize(
    ("socket_opened", "actual_bytes"),
    [(True, 0), (False, 1), (True, 1)],
)
def test_abandon_rejects_any_possible_network_consumption(
    socket_opened: bool,
    actual_bytes: int,
) -> None:
    reservation = AuthorizationConsumption.reserve(_reservation_request())
    settlement = ConsumptionSettlementRequest(
        authorization_id=reservation.authorization_id,
        request_attempt_id=reservation.request_attempt_id,
        actual_bytes=actual_bytes,
        socket_opened=socket_opened,
        state=ConsumptionState.ABANDONED,
        settled_at=reservation.reserved_at + timedelta(seconds=1),
    )

    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        AuthorizationConsumption.settle(reservation, settlement)

    assert exc_info.value.code == "AUTH_RESERVATION_INVALID"
