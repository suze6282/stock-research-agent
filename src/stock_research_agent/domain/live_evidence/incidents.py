"""Immutable incidents for controlled evidence operations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Literal, cast
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
)

from .exceptions import LiveEvidenceValidationError


class LiveIncidentWrite(FrozenProviderContract):
    category: Literal[
        "EVIDENCE_INTEGRITY",
        "AUTHORIZATION",
        "RETENTION",
        "PROVIDER_COMPLIANCE",
    ]
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    summary_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    affected_record_ids: tuple[UUID, ...] = Field(min_length=1, max_length=2048)
    source_checksum: Checksum
    opened_at: AwareUtcDateTime

    @field_validator("affected_record_ids")
    @classmethod
    def validate_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("affected IDs must be unique and sorted")
        return value


class LiveIncidentRecord(LiveIncidentWrite):
    id: UUID
    status: Literal["OPEN", "CONTAINED", "REMEDIATING", "CLOSED"]
    incident_checksum: Checksum
    updated_at: AwareUtcDateTime
    closed_at: AwareUtcDateTime | None = None


class LiveIncidentEventWrite(FrozenProviderContract):
    incident_id: UUID
    sequence: int = Field(ge=1, le=10000)
    event_type: Literal["CONTAIN", "START_REMEDIATION", "CLOSE"]
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    created_at: AwareUtcDateTime


class LiveIncidentEventRecord(LiveIncidentEventWrite):
    id: UUID
    previous_status: Literal["OPEN", "CONTAINED", "REMEDIATING"]
    target_status: Literal["CONTAINED", "REMEDIATING", "CLOSED"]


class IncidentTransitionResult(FrozenProviderContract):
    incident: LiveIncidentRecord
    event: LiveIncidentEventRecord


IncidentMutableStatus = Literal["OPEN", "CONTAINED", "REMEDIATING"]
IncidentTargetStatus = Literal["CONTAINED", "REMEDIATING", "CLOSED"]


class LiveIncidentRegistry:
    def __init__(self, *, id_factory: Callable[[], UUID] = uuid4) -> None:
        self._id_factory = id_factory

    def open(self, value: LiveIncidentWrite) -> LiveIncidentRecord:
        if any(item.int == 0 for item in value.affected_record_ids):
            raise LiveEvidenceValidationError("INCIDENT_SCOPE_INVALID")
        canonical = json.dumps(
            value.model_dump(mode="json", exclude={"opened_at"}),
            separators=(",", ":"),
            sort_keys=True,
        )
        return LiveIncidentRecord(
            **value.model_dump(),
            id=self._id_factory(),
            status="OPEN",
            incident_checksum=hashlib.sha256(canonical.encode("ascii")).hexdigest(),
            updated_at=value.opened_at,
        )

    def append_event(
        self,
        incident: LiveIncidentRecord,
        value: LiveIncidentEventWrite,
        *,
        existing: tuple[LiveIncidentEventRecord, ...],
    ) -> IncidentTransitionResult:
        if value.incident_id != incident.id or any(
            item.incident_id == value.incident_id and item.sequence == value.sequence
            for item in existing
        ):
            raise LiveEvidenceValidationError("INCIDENT_EVENT_DUPLICATE")
        transitions: dict[tuple[str, str], IncidentTargetStatus] = {
            ("OPEN", "CONTAIN"): "CONTAINED",
            ("CONTAINED", "START_REMEDIATION"): "REMEDIATING",
            ("REMEDIATING", "CLOSE"): "CLOSED",
        }
        target = transitions.get((incident.status, value.event_type))
        if target is None:
            raise LiveEvidenceValidationError("INCIDENT_TRANSITION_INVALID")
        previous = cast(IncidentMutableStatus, incident.status)
        event = LiveIncidentEventRecord(
            **value.model_dump(),
            id=self._id_factory(),
            previous_status=previous,
            target_status=target,
        )
        updated = incident.model_copy(
            update={
                "status": target,
                "updated_at": value.created_at,
                "closed_at": value.created_at if target == "CLOSED" else None,
            }
        )
        return IncidentTransitionResult(incident=updated, event=event)
