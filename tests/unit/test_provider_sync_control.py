from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.providers import sync as sync_contracts
from stock_research_agent.domain.providers.enums import (
    ProviderRunStatus,
    ProviderSyncSliceStatus,
)
from stock_research_agent.domain.providers.sync import (
    ProviderRequestAttemptWrite,
    ProviderRunTransition,
    ProviderSyncRunRecord,
)
from stock_research_agent.providers.control_plane import (
    ProviderSyncControlCommand,
    ProviderSyncControlService,
)

NOW = datetime(2026, 7, 29, 12, tzinfo=UTC)


def _run(status: ProviderRunStatus = ProviderRunStatus.RUNNING) -> ProviderSyncRunRecord:
    return ProviderSyncRunRecord(
        id=uuid4(),
        sync_request_id=uuid4(),
        sync_plan_id=uuid4(),
        provider_definition_id=uuid4(),
        provider_capability_id=uuid4(),
        status=status,
        consumed_requests=7,
        consumed_bytes=700,
        consumed_attempts=8,
        started_at=NOW,
        paused_at=None,
        completed_at=NOW
        if status
        in {
            ProviderRunStatus.COMPLETED,
            ProviderRunStatus.PARTIAL,
            ProviderRunStatus.BLOCKED,
            ProviderRunStatus.FAILED,
            ProviderRunStatus.CANCELLED,
        }
        else None,
        lease_owner="worker-1",
        lease_expires_at=NOW,
        warning_codes=("EXISTING",),
        created_at=NOW,
    )


class FakeControlRepository:
    def __init__(self, run: ProviderSyncRunRecord) -> None:
        self.run = run
        self.last_transition: ProviderRunTransition | None = None

    def get_run(self, run_id: object, *, for_update: bool = False) -> ProviderSyncRunRecord | None:
        assert for_update is True
        return self.run if run_id == self.run.id else None

    def transition(
        self,
        run_id: object,
        value: ProviderRunTransition,
    ) -> ProviderSyncRunRecord:
        assert run_id == self.run.id
        self.last_transition = value
        self.run = self.run.model_copy(
            update={
                "status": value.target,
                "consumed_requests": value.consumed_requests,
                "consumed_bytes": value.consumed_bytes,
                "consumed_attempts": value.consumed_attempts,
                "started_at": value.started_at,
                "paused_at": value.paused_at,
                "completed_at": value.completed_at,
                "lease_owner": value.lease_owner,
                "lease_expires_at": value.lease_expires_at,
                "warning_codes": value.warning_codes,
            }
        )
        return self.run


def _command(run: ProviderSyncRunRecord, **changes: object) -> ProviderSyncControlCommand:
    values: dict[str, object] = {
        "run_id": run.id,
        "sync_request_id": run.sync_request_id,
        "sync_plan_id": run.sync_plan_id,
        "provider_definition_id": run.provider_definition_id,
        "provider_capability_id": run.provider_capability_id,
    }
    values.update(changes)
    return ProviderSyncControlCommand.model_validate(values)


def test_pause_and_resume_preserve_budget_plan_and_context() -> None:
    repository = FakeControlRepository(_run())
    service = ProviderSyncControlService(repository, clock=lambda: NOW)
    command = _command(repository.run)

    paused = service.pause(command)
    resumed = service.resume(command)

    assert paused.status is ProviderRunStatus.PAUSED
    assert resumed.status is ProviderRunStatus.RUNNING
    assert resumed.consumed_requests == 7
    assert resumed.consumed_bytes == 700
    assert resumed.consumed_attempts == 8
    assert resumed.sync_plan_id == command.sync_plan_id


def test_cancel_preserves_counters_and_makes_run_terminal() -> None:
    repository = FakeControlRepository(_run())
    service = ProviderSyncControlService(repository, clock=lambda: NOW)
    cancelled = service.cancel(_command(repository.run))
    assert cancelled.status is ProviderRunStatus.CANCELLED
    assert cancelled.completed_at == NOW
    assert cancelled.consumed_requests == 7
    with pytest.raises(ValueError, match="TERMINAL"):
        service.resume(_command(cancelled))


@pytest.mark.parametrize(
    "field",
    (
        "sync_request_id",
        "sync_plan_id",
        "provider_definition_id",
        "provider_capability_id",
    ),
)
def test_control_rejects_cross_run_policy_plan_or_context_swap(field: str) -> None:
    repository = FakeControlRepository(_run())
    service = ProviderSyncControlService(repository, clock=lambda: NOW)
    with pytest.raises(ValueError, match="CONTEXT"):
        service.pause(_command(repository.run, **{field: uuid4()}))


def test_attempt_reservation_and_settlement_contracts_are_frozen_and_bounded() -> None:
    reservation_type = sync_contracts.ProviderRequestAttemptReservation
    settlement_type = sync_contracts.ProviderRequestAttemptSettlement
    attempt_id = UUID("80000000-0000-0000-0000-000000000001")
    write = ProviderRequestAttemptWrite(
        sync_run_id=uuid4(),
        slice_id="SEC_SUBMISSIONS",
        attempt_number=1,
        status=ProviderSyncSliceStatus.PENDING,
        endpoint_id="SEC_SUBMISSIONS_JSON",
        response_status_code=None,
        response_bytes=0,
        started_at=NOW,
    )

    reservation = reservation_type(id=attempt_id, value=write)
    settlement = settlement_type(
        id=attempt_id,
        status=ProviderSyncSliceStatus.COMPLETED,
        response_status_code=200,
        response_bytes=128,
        completed_at=NOW,
        safe_error_code=None,
    )

    assert reservation.id == settlement.id == attempt_id
    with pytest.raises(ValidationError):
        reservation.id = uuid4()
    with pytest.raises(ValidationError):
        settlement.status = ProviderSyncSliceStatus.PENDING
