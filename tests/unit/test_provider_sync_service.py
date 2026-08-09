from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from stock_research_agent.domain.providers.enums import ProviderRunStatus
from stock_research_agent.domain.providers.sync import (
    ProviderExecutionMode,
    ProviderSyncPlanDraft,
    ProviderSyncPlanRecord,
    ProviderSyncRequestRecord,
    ProviderSyncRequestWrite,
    ProviderSyncRunRecord,
    ProviderSyncRunWrite,
    ProviderSyncSlice,
)
from stock_research_agent.providers.control_plane import (
    ProviderSyncBlocked,
    ProviderSyncCommand,
    ProviderSyncGateDecision,
    ProviderSyncService,
)

NOW = datetime(2026, 7, 29, tzinfo=UTC)


class SpyGate:
    def __init__(self, events: list[str], name: str, *, allowed: bool = True) -> None:
        self.events = events
        self.name = name
        self.allowed = allowed

    def evaluate(self, command: ProviderSyncCommand) -> ProviderSyncGateDecision:
        del command
        self.events.append(f"gate:{self.name}")
        return ProviderSyncGateDecision(
            allowed=self.allowed,
            reason_code=f"{self.name}_{'ALLOWED' if self.allowed else 'BLOCKED'}",
        )


class FakeRepository:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.requests: dict[str, ProviderSyncRequestRecord] = {}
        self.plans: dict[str, ProviderSyncPlanRecord] = {}
        self.runs: dict[tuple[UUID, UUID], ProviderSyncRunRecord] = {}

    def create_request(self, value: ProviderSyncRequestWrite) -> ProviderSyncRequestRecord:
        self.events.append("repository:create_request")
        record = self.requests.get(value.idempotency_key)
        if record is None:
            record = ProviderSyncRequestRecord(
                **value.model_dump(),
                id=uuid4(),
                created_at=NOW,
            )
            self.requests[value.idempotency_key] = record
        return record

    def add_plan(self, value: object) -> ProviderSyncPlanRecord:
        from stock_research_agent.domain.providers.sync import ProviderSyncPlanWrite

        assert isinstance(value, ProviderSyncPlanWrite)
        self.events.append("repository:add_plan")
        record = self.plans.get(value.plan_checksum)
        if record is None:
            record = ProviderSyncPlanRecord(
                **value.model_dump(),
                id=uuid4(),
                slice_count=len(value.slices),
                created_at=NOW,
            )
            self.plans[value.plan_checksum] = record
        return record

    def create_run(self, value: ProviderSyncRunWrite) -> ProviderSyncRunRecord:
        self.events.append("repository:create_run")
        identity = (value.sync_request_id, value.sync_plan_id)
        record = self.runs.get(identity)
        if record is None:
            record = ProviderSyncRunRecord(
                **value.model_dump(),
                id=uuid4(),
                status=ProviderRunStatus.PLANNED,
                consumed_requests=0,
                consumed_bytes=0,
                consumed_attempts=0,
                started_at=None,
                paused_at=None,
                completed_at=None,
                lease_owner=None,
                lease_expires_at=None,
                warning_codes=(),
                created_at=NOW,
            )
            self.runs[identity] = record
        return record


class FakeAdapter:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def build_plan(
        self,
        request: ProviderSyncRequestRecord,
        catalog_version: str,
    ) -> ProviderSyncPlanDraft:
        self.events.append("adapter:plan")
        return ProviderSyncPlanDraft(
            sync_request_id=request.id,
            adapter_version="1.0.0",
            catalog_version=catalog_version,
            checkpoint_revision=0,
            slices=(
                ProviderSyncSlice(
                    slice_id="ONE",
                    ordinal=0,
                    range_start=request.range_start,
                    range_end=request.range_end,
                    request_parameters={"page": 1},
                ),
            ),
        )


class FakeExecutor:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def execute(
        self,
        run: ProviderSyncRunRecord,
        plan: ProviderSyncPlanRecord,
    ) -> ProviderRunStatus:
        del run, plan
        self.events.append("executor:execute")
        return ProviderRunStatus.COMPLETED


def _command(catalog_version: str = "1.0.0") -> ProviderSyncCommand:
    return ProviderSyncCommand(
        request=ProviderSyncRequestWrite(
            provider_definition_id=uuid4(),
            provider_capability_id=uuid4(),
            policy_id=uuid4(),
            license_policy_id=uuid4(),
            credential_reference_id=None,
            security_id=uuid4(),
            universe_code=None,
            research_as_of_time=NOW,
            range_start=date(2026, 7, 1),
            range_end=date(2026, 7, 29),
            execution_mode=ProviderExecutionMode.OFFLINE,
            scope={"security_scope": "EXACT"},
            budget={
                "max_requests": 2,
                "max_bytes": 1000,
                "max_attempts": 1,
                "max_duration_seconds": 30,
            },
            request_checksum="a" * 64,
            idempotency_key="b" * 64,
        ),
        catalog_version=catalog_version,
    )


def _service(events: list[str], *, blocked_gate: str | None = None) -> ProviderSyncService:
    gate_names = ("DEFINITION", "CAPABILITY", "LICENSE", "POLICY", "CONFIGURATION")
    return ProviderSyncService(
        repository=FakeRepository(events),
        adapter=FakeAdapter(events),
        executor=FakeExecutor(events),
        gates=tuple(SpyGate(events, name, allowed=name != blocked_gate) for name in gate_names),
        clock=lambda: NOW,
    )


def test_all_gates_run_before_request_plan_or_run_creation() -> None:
    events: list[str] = []
    result = _service(events).run(_command())
    assert result.status is ProviderRunStatus.COMPLETED
    assert events == [
        "gate:DEFINITION",
        "gate:CAPABILITY",
        "gate:LICENSE",
        "gate:POLICY",
        "gate:CONFIGURATION",
        "repository:create_request",
        "adapter:plan",
        "repository:add_plan",
        "repository:create_run",
        "executor:execute",
    ]


def test_blocked_gate_prevents_all_persistence_and_execution() -> None:
    events: list[str] = []
    with pytest.raises(ProviderSyncBlocked, match="LICENSE_BLOCKED"):
        _service(events, blocked_gate="LICENSE").run(_command())
    assert events == ["gate:DEFINITION", "gate:CAPABILITY", "gate:LICENSE"]


def test_catalog_version_change_produces_new_plan_and_run_identity() -> None:
    events: list[str] = []
    repository = FakeRepository(events)
    service = ProviderSyncService(
        repository=repository,
        adapter=FakeAdapter(events),
        executor=FakeExecutor(events),
        gates=(SpyGate(events, "ALLOW"),),
        clock=lambda: NOW,
    )
    first = service.run(_command("1.0.0"))
    second = service.run(_command("2.0.0"))
    assert first.plan.plan_checksum != second.plan.plan_checksum
    assert first.run.id != second.run.id
    assert len(repository.runs) == 2
