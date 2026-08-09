from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from stock_research_agent.domain.providers.canonical import provider_checksum
from stock_research_agent.domain.providers.enums import (
    ProviderRunStatus,
    ProviderSyncSliceStatus,
)
from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
    SemanticVersion,
)


class ProviderExecutionMode(StrEnum):
    OFFLINE = "OFFLINE"
    LIVE_VALIDATION = "LIVE_VALIDATION"


class ProviderRunContext(FrozenProviderContract):
    sync_request_id: UUID
    sync_plan_id: UUID
    policy_id: UUID
    license_policy_id: UUID
    max_requests: int = Field(ge=1, le=10_000)
    max_bytes: int = Field(ge=1, le=10_737_418_240)


class ProviderRunStateMachine:
    """Single deterministic transition map shared with the PostgreSQL guard."""

    _TERMINAL = frozenset(
        {
            ProviderRunStatus.COMPLETED,
            ProviderRunStatus.PARTIAL,
            ProviderRunStatus.BLOCKED,
            ProviderRunStatus.FAILED,
            ProviderRunStatus.CANCELLED,
        }
    )
    _ALLOWED = {
        ProviderRunStatus.PLANNED: frozenset(
            {
                ProviderRunStatus.QUEUED,
                ProviderRunStatus.BLOCKED,
                ProviderRunStatus.CANCELLED,
            }
        ),
        ProviderRunStatus.QUEUED: frozenset(
            {
                ProviderRunStatus.RUNNING,
                ProviderRunStatus.BLOCKED,
                ProviderRunStatus.CANCELLED,
            }
        ),
        ProviderRunStatus.RUNNING: frozenset(
            {
                ProviderRunStatus.PAUSED,
                ProviderRunStatus.COMPLETED,
                ProviderRunStatus.PARTIAL,
                ProviderRunStatus.BLOCKED,
                ProviderRunStatus.FAILED,
                ProviderRunStatus.CANCELLED,
            }
        ),
        ProviderRunStatus.PAUSED: frozenset(
            {
                ProviderRunStatus.QUEUED,
                ProviderRunStatus.RUNNING,
                ProviderRunStatus.BLOCKED,
                ProviderRunStatus.CANCELLED,
            }
        ),
    }

    @classmethod
    def transition(
        cls,
        current: ProviderRunStatus,
        target: ProviderRunStatus,
    ) -> ProviderRunStatus:
        if current in cls._TERMINAL:
            raise ValueError("PROVIDER_RUN_TERMINAL")
        if target is current:
            return target
        if target not in cls._ALLOWED.get(current, frozenset()):
            raise ValueError("PROVIDER_RUN_TRANSITION_FORBIDDEN")
        return target

    @classmethod
    def validate_context_unchanged(
        cls,
        current: ProviderRunContext,
        proposed: ProviderRunContext,
    ) -> None:
        if current != proposed:
            raise ValueError("PROVIDER_RUN_CONTEXT_IMMUTABLE")

    @classmethod
    def allowed_transitions(
        cls,
    ) -> dict[ProviderRunStatus, frozenset[ProviderRunStatus]]:
        return dict(cls._ALLOWED)


class CheckpointScope(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    universe_code: str | None = Field(default=None, min_length=1, max_length=64)
    security_id: UUID | None = None
    scope_version: SemanticVersion

    @model_validator(mode="after")
    def validate_exact_scope(self) -> CheckpointScope:
        if (self.universe_code is None) == (self.security_id is None):
            raise ValueError("exactly one universe_code or security_id is required")
        return self

    def checksum(self) -> str:
        return provider_checksum(self.model_dump(mode="json"))


class CheckpointAdvance(FrozenProviderContract):
    scope: CheckpointScope
    expected_revision: int = Field(ge=0)
    watermark: dict[str, object]


class ProviderCheckpointRecord(FrozenProviderContract):
    id: UUID
    scope: CheckpointScope
    scope_checksum: Checksum
    watermark: dict[str, object]
    revision: int = Field(ge=0)
    updated_at: AwareUtcDateTime
    created_at: AwareUtcDateTime


class ProviderSyncRequestWrite(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    policy_id: UUID
    license_policy_id: UUID
    credential_reference_id: UUID | None
    security_id: UUID | None = None
    universe_code: str | None = Field(default=None, min_length=1, max_length=64)
    research_as_of_time: AwareUtcDateTime
    range_start: date
    range_end: date
    execution_mode: ProviderExecutionMode
    scope: dict[str, object]
    budget: dict[str, object]
    request_checksum: Checksum
    idempotency_key: Checksum

    @model_validator(mode="after")
    def validate_range_and_scope(self) -> ProviderSyncRequestWrite:
        if self.range_end < self.range_start:
            raise ValueError("range_end cannot precede range_start")
        if self.range_end > self.research_as_of_time.date():
            raise ValueError("FUTURE range is not allowed")
        if (self.security_id is None) == (self.universe_code is None):
            raise ValueError("exactly one Security or universe scope is required")
        if self.universe_code is not None and self.universe_code.casefold() == "latest":
            raise ValueError("LATEST is not an exact universe")
        if _contains_arbitrary_input(self.scope):
            raise ValueError("ARBITRARY URL, path, or SQL scope is forbidden")
        _validate_finite_budget(self.budget)
        return self


class ProviderSyncRequestRecord(ProviderSyncRequestWrite):
    id: UUID
    created_at: AwareUtcDateTime


class ProviderSyncSlice(FrozenProviderContract):
    slice_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    ordinal: int = Field(ge=0, le=9_999)
    range_start: date
    range_end: date
    depends_on: tuple[str, ...] = Field(default=(), max_length=64)
    request_parameters: dict[str, object]

    @model_validator(mode="after")
    def validate_slice(self) -> ProviderSyncSlice:
        if self.range_end < self.range_start:
            raise ValueError("slice range_end cannot precede range_start")
        if self.slice_id in self.depends_on:
            raise ValueError("slice cannot depend on itself")
        if self.depends_on != tuple(sorted(set(self.depends_on))):
            raise ValueError("slice dependencies must be unique and sorted")
        context_keys = {
            "provider_definition_id",
            "provider_capability_id",
            "security_id",
            "universe_code",
            "snapshot_id",
            "research_as_of_time",
            "policy_id",
            "license_policy_id",
            "credential_reference_id",
        }
        if context_keys.intersection(self.request_parameters):
            raise ValueError("CONTEXT override is forbidden")
        if _contains_arbitrary_input(self.request_parameters):
            raise ValueError("ARBITRARY URL, path, or SQL input is forbidden")
        return self


class ProviderSyncPlanDraft(FrozenProviderContract):
    sync_request_id: UUID
    adapter_version: SemanticVersion
    catalog_version: SemanticVersion
    checkpoint_revision: int | None = Field(default=None, ge=0)
    slices: tuple[ProviderSyncSlice, ...] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def validate_finite_dag(self) -> ProviderSyncPlanDraft:
        ids = tuple(item.slice_id for item in self.slices)
        if len(ids) != len(set(ids)):
            raise ValueError("slice identifiers must be unique")
        if tuple(item.ordinal for item in self.slices) != tuple(range(len(self.slices))):
            raise ValueError("slice ordinals must be contiguous and ordered")
        positions = {item.slice_id: item.ordinal for item in self.slices}
        for item in self.slices:
            for dependency in item.depends_on:
                if dependency not in positions:
                    raise ValueError("slice dependency is undefined")
                if positions[dependency] >= item.ordinal:
                    raise ValueError("slice dependency must precede the dependent slice")
        return self

    def to_write(self) -> ProviderSyncPlanWrite:
        return ProviderSyncPlanWrite(
            sync_request_id=self.sync_request_id,
            adapter_version=self.adapter_version,
            checkpoint_revision=self.checkpoint_revision,
            slices=tuple(item.model_dump(mode="json") for item in self.slices),
            plan_checksum=build_plan_checksum(self),
        )


def build_plan_checksum(value: ProviderSyncPlanDraft) -> str:
    return provider_checksum(value)


class ProviderSyncPlanWrite(FrozenProviderContract):
    sync_request_id: UUID
    adapter_version: SemanticVersion
    checkpoint_revision: int | None = Field(default=None, ge=0)
    slices: tuple[dict[str, object], ...] = Field(min_length=1, max_length=10_000)
    plan_checksum: Checksum


class ProviderSyncPlanRecord(ProviderSyncPlanWrite):
    id: UUID
    slice_count: int = Field(ge=1, le=10_000)
    created_at: AwareUtcDateTime


class ProviderSyncRunWrite(FrozenProviderContract):
    sync_request_id: UUID
    sync_plan_id: UUID
    provider_definition_id: UUID
    provider_capability_id: UUID


class ProviderSyncRunRecord(ProviderSyncRunWrite):
    id: UUID
    status: ProviderRunStatus
    consumed_requests: int = Field(ge=0)
    consumed_bytes: int = Field(ge=0)
    consumed_attempts: int = Field(ge=0)
    started_at: AwareUtcDateTime | None
    paused_at: AwareUtcDateTime | None
    completed_at: AwareUtcDateTime | None
    lease_owner: str | None
    lease_expires_at: AwareUtcDateTime | None
    warning_codes: tuple[str, ...]
    created_at: AwareUtcDateTime


class ProviderRunTransition(FrozenProviderContract):
    target: ProviderRunStatus
    consumed_requests: int = Field(default=0, ge=0)
    consumed_bytes: int = Field(default=0, ge=0)
    consumed_attempts: int = Field(default=0, ge=0)
    started_at: AwareUtcDateTime | None = None
    paused_at: AwareUtcDateTime | None = None
    completed_at: AwareUtcDateTime | None = None
    lease_owner: str | None = Field(default=None, max_length=128)
    lease_expires_at: AwareUtcDateTime | None = None
    warning_codes: tuple[str, ...] = Field(default=(), max_length=64)


class ProviderRequestAttemptWrite(FrozenProviderContract):
    sync_run_id: UUID
    slice_id: str = Field(min_length=1, max_length=64)
    attempt_number: int = Field(ge=1, le=3)
    status: ProviderSyncSliceStatus
    endpoint_id: str = Field(min_length=1, max_length=128)
    response_status_code: int | None = Field(default=None, ge=100, le=599)
    response_bytes: int = Field(ge=0)
    started_at: AwareUtcDateTime
    completed_at: AwareUtcDateTime | None = None
    safe_error_code: str | None = Field(default=None, max_length=128)


class ProviderRequestAttemptRecord(ProviderRequestAttemptWrite):
    id: UUID
    created_at: AwareUtcDateTime


_SQL = re.compile(r"(?i)\b(?:select|insert|update|delete|drop|alter|create)\b")
_FORBIDDEN_SCOPE_KEYS = frozenset({"url", "uri", "path", "file", "sql", "query"})
_BUDGET_BOUNDS = {
    "max_requests": (1, 10_000),
    "max_bytes": (1, 10_737_418_240),
    "max_attempts": (1, 3),
    "max_duration_seconds": (1, 86_400),
}


def _contains_arbitrary_input(value: object, *, key: str | None = None) -> bool:
    if key is not None and key.casefold() in _FORBIDDEN_SCOPE_KEYS:
        return True
    if isinstance(value, dict):
        return any(
            _contains_arbitrary_input(item, key=str(item_key)) for item_key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_arbitrary_input(item) for item in value)
    if not isinstance(value, str):
        return False
    lowered = value.casefold()
    return (
        "://" in lowered
        or lowered.startswith(("/", "\\"))
        or re.match(r"^[a-zA-Z]:[\\/]", value) is not None
        or _SQL.search(value) is not None
        or lowered == "latest"
    )


def _validate_finite_budget(value: dict[str, object]) -> None:
    if set(value) != set(_BUDGET_BOUNDS):
        raise ValueError("BUDGET must contain the exact finite limit set")
    for name, (minimum, maximum) in _BUDGET_BOUNDS.items():
        item = value[name]
        if isinstance(item, bool) or not isinstance(item, int) or not minimum <= item <= maximum:
            raise ValueError(f"BUDGET {name} is outside its finite bound")
