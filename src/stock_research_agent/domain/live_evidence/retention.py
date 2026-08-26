"""Deterministic retention plans and restricted-artifact deletion ports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)

from .exceptions import LiveEvidenceValidationError


class EvidenceRetentionPlanRequest(FrozenProviderContract):
    action_type: Literal["DELETE_RESTRICTED_ARTIFACT"]
    artifact_ids: tuple[UUID, ...] = Field(min_length=1, max_length=128)
    affected_lineage_ids: tuple[UUID, ...] = Field(max_length=2048)
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    deadline_at: AwareUtcDateTime
    created_at: AwareUtcDateTime

    @field_validator("artifact_ids", "affected_lineage_ids")
    @classmethod
    def validate_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("IDs must be unique and sorted")
        return value


class EvidenceRetentionActionRecord(EvidenceRetentionPlanRequest):
    id: UUID
    status: Literal["PLANNED", "RUNNING", "PASS", "PARTIAL", "BLOCKED", "FAIL"]
    plan_checksum: Checksum
    completed_at: AwareUtcDateTime | None = None
    warning_codes: tuple[str, ...] = ()


class EvidenceRetentionRegistry:
    def __init__(self, *, id_factory: Callable[[], UUID] = uuid4) -> None:
        self._id_factory = id_factory

    def plan(self, value: EvidenceRetentionPlanRequest) -> EvidenceRetentionActionRecord:
        if any(item.int == 0 for item in value.artifact_ids):
            raise LiveEvidenceValidationError("RETENTION_SCOPE_INVALID")
        if value.deadline_at <= value.created_at:
            raise LiveEvidenceValidationError("RETENTION_DEADLINE_INVALID")
        canonical = json.dumps(
            value.model_dump(mode="json", exclude={"created_at"}),
            separators=(",", ":"),
            sort_keys=True,
        )
        return EvidenceRetentionActionRecord(
            **value.model_dump(),
            id=self._id_factory(),
            status="PLANNED",
            plan_checksum=hashlib.sha256(canonical.encode("ascii")).hexdigest(),
        )

    def execute(
        self,
        action: EvidenceRetentionActionRecord,
        *,
        storage: RestrictedArtifactStorage,
        completed_at: AwareUtcDateTime,
    ) -> EvidenceRetentionActionRecord:
        if action.status != "PLANNED":
            raise LiveEvidenceValidationError("RETENTION_HISTORY_REWRITE_FORBIDDEN")
        try:
            for artifact_id in action.artifact_ids:
                storage.delete(artifact_id)
        except Exception as exc:
            raise LiveEvidenceValidationError("RETENTION_DELETE_BLOCKED") from exc
        if any(storage.exists(artifact_id) for artifact_id in action.artifact_ids):
            raise LiveEvidenceValidationError("RETENTION_DELETE_VERIFY_FAILED")
        return action.model_copy(
            update={
                "status": "PASS",
                "completed_at": completed_at,
            }
        )


class RestrictedArtifactStorage(Protocol):
    def delete(self, artifact_id: UUID) -> None: ...

    def exists(self, artifact_id: UUID) -> bool: ...
