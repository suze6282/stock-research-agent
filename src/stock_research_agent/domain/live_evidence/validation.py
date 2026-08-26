"""Immutable Gate A validation runs and append-only check records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)

from .exceptions import LiveEvidenceValidationError

ValidationRunStatus = Literal[
    "PLANNED", "RUNNING", "PASS", "PARTIAL", "BLOCKED", "FAIL", "CANCELLED"
]
_TERMINAL = {"PASS", "PARTIAL", "BLOCKED", "FAIL", "CANCELLED"}
_TRANSITIONS: dict[str, frozenset[str]] = {
    "PLANNED": frozenset({"RUNNING", "BLOCKED", "CANCELLED"}),
    "RUNNING": frozenset(_TERMINAL),
}


class RealCompanyValidationRunWrite(FrozenProviderContract):
    security_id: UUID
    snapshot_id: UUID
    research_agent_run_id: UUID
    report_id: UUID
    research_as_of_time: AwareUtcDateTime
    validation_policy_version: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,127}$")
    input_checksums: tuple[Checksum, ...] = Field(min_length=1, max_length=128)
    created_at: AwareUtcDateTime

    @field_validator("input_checksums")
    @classmethod
    def validate_checksums(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("input checksums must be unique and sorted")
        return value


class RealCompanyValidationRunRecord(RealCompanyValidationRunWrite):
    id: UUID
    status: ValidationRunStatus
    input_checksum: Checksum
    updated_at: AwareUtcDateTime
    terminal_at: AwareUtcDateTime | None = None


class EndToEndValidationCheckWrite(FrozenProviderContract):
    validation_run_id: UUID
    sequence: int = Field(ge=1, le=100)
    stage_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    status: Literal["PASS", "PARTIAL", "BLOCKED", "NOT_ATTEMPTED", "FAIL"]
    evidence_record_type: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    evidence_record_id: UUID
    evidence_checksum: Checksum
    reason_codes: tuple[str, ...] = Field(max_length=100)
    created_at: AwareUtcDateTime

    @field_validator("reason_codes")
    @classmethod
    def validate_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("reason codes must be unique and sorted")
        return value


class EndToEndValidationCheckRecord(EndToEndValidationCheckWrite):
    id: UUID


class EndToEndValidationRegistry:
    def __init__(self, *, id_factory: Callable[[], UUID] = uuid4) -> None:
        self._id_factory = id_factory

    def append(
        self,
        value: EndToEndValidationCheckWrite,
        *,
        existing: tuple[EndToEndValidationCheckRecord, ...],
    ) -> EndToEndValidationCheckRecord:
        if value.evidence_record_id.int == 0 or value.validation_run_id.int == 0:
            raise LiveEvidenceValidationError("VALIDATION_EVIDENCE_INVALID")
        if any(
            item.validation_run_id == value.validation_run_id
            and item.stage_code == value.stage_code
            for item in existing
        ):
            raise LiveEvidenceValidationError("VALIDATION_CHECK_DUPLICATE")
        if any(
            item.validation_run_id == value.validation_run_id and item.sequence == value.sequence
            for item in existing
        ):
            raise LiveEvidenceValidationError("VALIDATION_CHECK_DUPLICATE")
        return EndToEndValidationCheckRecord(
            **value.model_dump(),
            id=self._id_factory(),
        )


class ValidationRunRegistry:
    def __init__(self, *, id_factory: Callable[[], UUID] = uuid4) -> None:
        self._id_factory = id_factory

    def create(self, value: RealCompanyValidationRunWrite) -> RealCompanyValidationRunRecord:
        if any(
            item.int == 0
            for item in (
                value.security_id,
                value.snapshot_id,
                value.research_agent_run_id,
                value.report_id,
            )
        ):
            raise LiveEvidenceValidationError("VALIDATION_SCOPE_INVALID")
        checksum = _checksum(value.model_dump(mode="json", exclude={"created_at"}))
        return RealCompanyValidationRunRecord(
            **value.model_dump(),
            id=self._id_factory(),
            status="PLANNED",
            input_checksum=checksum,
            updated_at=value.created_at,
        )

    def transition(
        self,
        run: RealCompanyValidationRunRecord,
        target: ValidationRunStatus,
        *,
        changed_at: AwareUtcDateTime,
    ) -> RealCompanyValidationRunRecord:
        if run.status in _TERMINAL:
            raise LiveEvidenceValidationError("VALIDATION_TERMINAL_IMMUTABLE")
        if target not in _TRANSITIONS.get(run.status, frozenset()):
            raise LiveEvidenceValidationError("VALIDATION_TRANSITION_INVALID")
        return run.model_copy(
            update={
                "status": target,
                "updated_at": changed_at,
                "terminal_at": changed_at if target in _TERMINAL else None,
            }
        )


def _checksum(payload: object) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()
