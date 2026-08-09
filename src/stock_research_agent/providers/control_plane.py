"""Transaction-neutral orchestration for governed Provider synchronization."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_research_agent.db.models.providers import ProviderSyncRequest, ProviderSyncRun
from stock_research_agent.domain.providers.enums import ProviderRunStatus
from stock_research_agent.domain.providers.repositories import ProviderSyncRepository
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    FrozenProviderContract,
    SemanticVersion,
)
from stock_research_agent.domain.providers.sync import (
    ProviderRunStateMachine,
    ProviderRunTransition,
    ProviderSyncPlanDraft,
    ProviderSyncPlanRecord,
    ProviderSyncRequestRecord,
    ProviderSyncRequestWrite,
    ProviderSyncRunRecord,
    ProviderSyncRunWrite,
)


class ProviderSyncGateDecision(FrozenProviderContract):
    allowed: bool
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")


class ProviderSyncCommand(FrozenProviderContract):
    request: ProviderSyncRequestWrite
    catalog_version: SemanticVersion


class ProviderSyncResult(FrozenProviderContract):
    status: ProviderRunStatus
    request: ProviderSyncRequestRecord
    plan: ProviderSyncPlanRecord
    run: ProviderSyncRunRecord
    evaluated_at: AwareUtcDateTime


class ProviderSyncGate(Protocol):
    def evaluate(self, command: ProviderSyncCommand) -> ProviderSyncGateDecision: ...


class ProviderSyncAdapter(Protocol):
    def build_plan(
        self,
        request: ProviderSyncRequestRecord,
        catalog_version: str,
    ) -> ProviderSyncPlanDraft: ...


class ProviderSyncExecutor(Protocol):
    def execute(
        self,
        run: ProviderSyncRunRecord,
        plan: ProviderSyncPlanRecord,
    ) -> ProviderRunStatus: ...


class ProviderSyncBlocked(Exception):
    """Safe fail-closed signal raised before any persistence or execution."""


class ProviderSyncService:
    """Coordinate finite sync work while leaving transaction ownership to callers."""

    def __init__(
        self,
        *,
        repository: ProviderSyncRepository,
        adapter: ProviderSyncAdapter,
        executor: ProviderSyncExecutor,
        gates: tuple[ProviderSyncGate, ...],
        clock: Callable[[], AwareUtcDateTime],
    ) -> None:
        if not gates:
            raise ValueError("at least one Provider sync gate is required")
        self._repository = repository
        self._adapter = adapter
        self._executor = executor
        self._gates = gates
        self._clock = clock

    def plan(self, command: ProviderSyncCommand) -> ProviderSyncPlanRecord:
        _, plan = self._prepare(command)
        return plan

    def run(self, command: ProviderSyncCommand) -> ProviderSyncResult:
        evaluated_at = self._clock()
        request, plan = self._prepare(command)
        run = self._repository.create_run(
            ProviderSyncRunWrite(
                sync_request_id=request.id,
                sync_plan_id=plan.id,
                provider_definition_id=request.provider_definition_id,
                provider_capability_id=request.provider_capability_id,
            )
        )
        status = self._executor.execute(run, plan)
        return ProviderSyncResult(
            status=status,
            request=request,
            plan=plan,
            run=run,
            evaluated_at=evaluated_at,
        )

    def _prepare(
        self,
        command: ProviderSyncCommand,
    ) -> tuple[ProviderSyncRequestRecord, ProviderSyncPlanRecord]:
        for gate in self._gates:
            decision = gate.evaluate(command)
            if not decision.allowed:
                raise ProviderSyncBlocked(decision.reason_code)

        request = self._repository.create_request(command.request)
        draft = self._adapter.build_plan(request, command.catalog_version)
        if draft.sync_request_id != request.id:
            raise ValueError("PROVIDER_PLAN_REQUEST_MISMATCH")
        if draft.catalog_version != command.catalog_version:
            raise ValueError("PROVIDER_PLAN_CATALOG_MISMATCH")
        plan = self._repository.add_plan(draft.to_write())
        return request, plan


class ProviderSyncControlCommand(FrozenProviderContract):
    run_id: UUID
    sync_request_id: UUID
    sync_plan_id: UUID
    provider_definition_id: UUID
    provider_capability_id: UUID


class ProviderSyncControlRepository(Protocol):
    def get_run(
        self,
        run_id: UUID,
        *,
        for_update: bool = False,
    ) -> ProviderSyncRunRecord | None: ...

    def transition(
        self,
        run_id: UUID,
        value: ProviderRunTransition,
    ) -> ProviderSyncRunRecord: ...


class ProviderSyncControlService:
    """Apply context-bound lifecycle controls without resetting consumed state."""

    def __init__(
        self,
        repository: ProviderSyncControlRepository,
        *,
        clock: Callable[[], AwareUtcDateTime],
    ) -> None:
        self._repository = repository
        self._clock = clock

    def pause(self, command: ProviderSyncControlCommand) -> ProviderSyncRunRecord:
        return self._change(command, ProviderRunStatus.PAUSED)

    def resume(self, command: ProviderSyncControlCommand) -> ProviderSyncRunRecord:
        return self._change(command, ProviderRunStatus.RUNNING)

    def cancel(self, command: ProviderSyncControlCommand) -> ProviderSyncRunRecord:
        return self._change(command, ProviderRunStatus.CANCELLED)

    def _change(
        self,
        command: ProviderSyncControlCommand,
        target: ProviderRunStatus,
    ) -> ProviderSyncRunRecord:
        run = self._repository.get_run(command.run_id, for_update=True)
        if run is None:
            raise LookupError("PROVIDER_SYNC_RUN_NOT_FOUND")
        expected = (
            command.sync_request_id,
            command.sync_plan_id,
            command.provider_definition_id,
            command.provider_capability_id,
        )
        actual = (
            run.sync_request_id,
            run.sync_plan_id,
            run.provider_definition_id,
            run.provider_capability_id,
        )
        if actual != expected:
            raise ValueError("PROVIDER_RUN_CONTEXT_IMMUTABLE")
        ProviderRunStateMachine.transition(run.status, target)
        now = self._clock()
        return self._repository.transition(
            run.id,
            ProviderRunTransition(
                target=target,
                consumed_requests=run.consumed_requests,
                consumed_bytes=run.consumed_bytes,
                consumed_attempts=run.consumed_attempts,
                started_at=run.started_at,
                paused_at=now if target is ProviderRunStatus.PAUSED else None,
                completed_at=(now if target is ProviderRunStatus.CANCELLED else run.completed_at),
                lease_owner=(None if target is ProviderRunStatus.PAUSED else run.lease_owner),
                lease_expires_at=(
                    None if target is ProviderRunStatus.PAUSED else run.lease_expires_at
                ),
                warning_codes=run.warning_codes,
            ),
        )


class ProviderBudgetSnapshot(FrozenProviderContract):
    run_id: UUID
    max_requests: int = Field(ge=1, le=10_000)
    max_bytes: int = Field(ge=1, le=10_737_418_240)
    max_attempts: int = Field(ge=1, le=3)
    max_duration_seconds: int = Field(ge=1, le=86_400)
    consumed_requests: int = Field(ge=0)
    consumed_bytes: int = Field(ge=0)
    consumed_attempts: int = Field(ge=0)
    started_at: AwareUtcDateTime


class ProviderBudgetReservation(FrozenProviderContract):
    allowed: bool
    reason_code: str
    consumed_requests: int = Field(ge=0)
    consumed_bytes: int = Field(ge=0)
    consumed_attempts: int = Field(ge=0)


class ProviderBudgetStore(Protocol):
    def reserve(
        self,
        run_id: UUID,
        request_bytes: int,
        now: datetime,
    ) -> ProviderBudgetReservation: ...


class ProviderBudgetLedger:
    def __init__(
        self,
        store: ProviderBudgetStore,
        *,
        clock: Callable[[], AwareUtcDateTime],
    ) -> None:
        self._store = store
        self._clock = clock

    def reserve(self, run_id: UUID, *, request_bytes: int) -> ProviderBudgetReservation:
        if not 0 <= request_bytes <= 52_428_800:
            raise ValueError("request_bytes is outside the bounded response size")
        return self._store.reserve(run_id, request_bytes, self._clock())


class InMemoryProviderBudgetStore:
    def __init__(self, snapshots: dict[UUID, ProviderBudgetSnapshot]) -> None:
        self._snapshots = dict(snapshots)
        self._lock = threading.Lock()

    def reserve(
        self,
        run_id: UUID,
        request_bytes: int,
        now: datetime,
    ) -> ProviderBudgetReservation:
        with self._lock:
            snapshot = self._snapshots.get(run_id)
            if snapshot is None:
                raise LookupError("PROVIDER_SYNC_RUN_NOT_FOUND")
            result, updated = _reserve_budget(snapshot, request_bytes, now)
            self._snapshots[run_id] = updated
            return result


class PostgresProviderBudgetStore:
    """Reserve budget under a row lock in the caller-owned transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def reserve(
        self,
        run_id: UUID,
        request_bytes: int,
        now: datetime,
    ) -> ProviderBudgetReservation:
        row = self._session.execute(
            select(ProviderSyncRun, ProviderSyncRequest)
            .join(
                ProviderSyncRequest,
                ProviderSyncRequest.id == ProviderSyncRun.sync_request_id,
            )
            .where(ProviderSyncRun.id == run_id)
            .with_for_update(of=ProviderSyncRun)
        ).one_or_none()
        if row is None:
            raise LookupError("PROVIDER_SYNC_RUN_NOT_FOUND")
        run, request = row
        if ProviderRunStatus(run.status) is not ProviderRunStatus.RUNNING:
            return ProviderBudgetReservation(
                allowed=False,
                reason_code="PROVIDER_RUN_NOT_RUNNING",
                consumed_requests=run.consumed_requests,
                consumed_bytes=run.consumed_bytes,
                consumed_attempts=run.consumed_attempts,
            )
        budget = request.budget
        snapshot = ProviderBudgetSnapshot(
            run_id=run.id,
            max_requests=int(budget["max_requests"]),
            max_bytes=int(budget["max_bytes"]),
            max_attempts=int(budget["max_attempts"]),
            max_duration_seconds=int(budget["max_duration_seconds"]),
            consumed_requests=run.consumed_requests,
            consumed_bytes=run.consumed_bytes,
            consumed_attempts=run.consumed_attempts,
            started_at=(
                run.started_at.replace(tzinfo=UTC)
                if run.started_at.tzinfo is None
                else run.started_at.astimezone(UTC)
            ),
        )
        result, updated = _reserve_budget(snapshot, request_bytes, now)
        if result.allowed:
            run.consumed_requests = updated.consumed_requests
            run.consumed_bytes = updated.consumed_bytes
            run.consumed_attempts = updated.consumed_attempts
            self._session.flush()
        return result


def _reserve_budget(
    snapshot: ProviderBudgetSnapshot,
    request_bytes: int,
    now: datetime,
) -> tuple[ProviderBudgetReservation, ProviderBudgetSnapshot]:
    if (now - snapshot.started_at).total_seconds() >= snapshot.max_duration_seconds:
        reason = "PROVIDER_DURATION_EXHAUSTED"
    elif (
        snapshot.consumed_requests + 1 > snapshot.max_requests
        or snapshot.consumed_bytes + request_bytes > snapshot.max_bytes
        or snapshot.consumed_attempts + 1 > snapshot.max_attempts
    ):
        reason = "PROVIDER_BUDGET_EXHAUSTED"
    else:
        updated = snapshot.model_copy(
            update={
                "consumed_requests": snapshot.consumed_requests + 1,
                "consumed_bytes": snapshot.consumed_bytes + request_bytes,
                "consumed_attempts": snapshot.consumed_attempts + 1,
            }
        )
        return (
            ProviderBudgetReservation(
                allowed=True,
                reason_code="PROVIDER_BUDGET_RESERVED",
                consumed_requests=updated.consumed_requests,
                consumed_bytes=updated.consumed_bytes,
                consumed_attempts=updated.consumed_attempts,
            ),
            updated,
        )
    return (
        ProviderBudgetReservation(
            allowed=False,
            reason_code=reason,
            consumed_requests=snapshot.consumed_requests,
            consumed_bytes=snapshot.consumed_bytes,
            consumed_attempts=snapshot.consumed_attempts,
        ),
        snapshot,
    )
