from __future__ import annotations

import inspect

from stock_research_agent.db.repositories import live_evidence
from stock_research_agent.domain.live_evidence.enums import LiveAuthorizationEventType
from stock_research_agent.domain.live_evidence.gate_b_authorization import (
    AuthorizedGateBExecution,
    ProductionAuthorizationGate,
)
from tests.unit.test_gate_b_production_authorization_red import (
    NOW,
    _authoritative_records,
    _authorization_create_payload,
    _production_authorization_create,
)


def test_red_050_execution_start_is_authoritative_and_returns_no_early_capability() -> None:
    """GBR-01: caller state cannot replace the committed execution-start transaction."""

    gate_parameters = inspect.signature(ProductionAuthorizationGate.authorize).parameters
    assert "approval_consumed" not in gate_parameters, (
        "caller-supplied approval consumption is still accepted as authoritative"
    )

    start_execution = getattr(
        live_evidence.SqlAlchemySecAttemptReservationPort,
        "start_execution",
        None,
    )
    assert callable(start_execution), (
        "PostgreSQL reservation owner has no atomic approval/grant/run execution-start operation"
    )


def test_red_053_abandoned_consumption_is_counted_by_authoritative_request_query() -> None:
    """GBR-02: ABANDONED is permanent capacity lineage, never a query refund."""

    source = inspect.getsource(live_evidence.reserve_consumption)
    assert "state <> 'ABANDONED'" not in source, (
        "authoritative request counting still excludes ABANDONED reservations"
    )


def test_red_054_same_authorized_execution_cannot_replay_after_terminal_abandonment() -> None:
    """GBR-02: one approval snapshot cannot mint two early execution capabilities."""

    grant, approval, plan, scope, reference = _authoritative_records()
    envelope = _production_authorization_create()(
        _authorization_create_payload(grant_id=str(grant.id))
    )
    kwargs: dict[str, object] = {
        "grant": grant,
        "events": (LiveAuthorizationEventType.APPROVE, LiveAuthorizationEventType.ACTIVATE),
        "approval": approval,
        "plan": plan,
        "scope": scope,
        "contact_reference": reference,
        "checked_at": NOW,
    }
    if "approval_consumed" in inspect.signature(ProductionAuthorizationGate.authorize).parameters:
        kwargs["approval_consumed"] = False

    gate = ProductionAuthorizationGate()
    capabilities = tuple(gate.authorize(envelope, **kwargs) for _index in range(2))

    assert not all(isinstance(value, AuthorizedGateBExecution) for value in capabilities), (
        "the same unconsumed approval snapshot minted two executable capabilities"
    )
