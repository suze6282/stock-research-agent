"""Immutable Observation construction from validated Tool output."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import NoReturn, cast
from uuid import UUID

from pydantic import JsonValue, ValidationError

from stock_research_agent.domain.research_agent.canonical import (
    canonical_json,
    stable_checksum,
)
from stock_research_agent.domain.research_agent.enums import (
    ObservationStatus,
    ObservationType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ControlledRunContext,
    ResearchObservationWrite,
)


class ResearchObservationError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ResearchObservationBuilder:
    """Build a bounded JSON Observation bound to one controlled Run."""

    def build(
        self,
        *,
        observation_id: UUID,
        context: ControlledRunContext,
        invocation_id: UUID,
        observation_type: ObservationType,
        status: ObservationStatus,
        schema_version: str,
        payload: Mapping[str, object],
        synthetic_status: SyntheticStatus,
        warnings: Sequence[str],
        created_at: datetime,
    ) -> ResearchObservationWrite:
        if observation_type is ObservationType.TOOL_ERROR and status is not ObservationStatus.FAIL:
            _reject("INVALID_TOOL_ERROR_OBSERVATION")
        if observation_type is ObservationType.BLOCKED_CAPABILITY:
            if status is not ObservationStatus.BLOCKED or "capability_code" not in payload:
                _reject("INVALID_BLOCKED_OBSERVATION")

        try:
            serialized = canonical_json(payload)
        except (TypeError, ValueError):
            _reject("INVALID_OBSERVATION_OUTPUT")
        if len(serialized.encode("utf-8")) > 262_144:
            _reject("OBSERVATION_OUTPUT_TOO_LARGE")
        normalized = json.loads(serialized)
        if not isinstance(normalized, dict):
            _reject("INVALID_OBSERVATION_OUTPUT")

        try:
            return ResearchObservationWrite(
                id=observation_id,
                run_id=context.research_agent_run_id,
                invocation_id=invocation_id,
                observation_type=observation_type,
                status=status,
                schema_version=schema_version,
                payload=cast(dict[str, JsonValue], normalized),
                output_checksum=stable_checksum(payload),
                security_id=context.security_id,
                snapshot_id=context.snapshot_id,
                research_as_of_time=context.research_as_of_time,
                synthetic_status=synthetic_status,
                warnings=tuple(warnings),
                created_at=created_at,
            )
        except ValidationError:
            _reject("INVALID_OBSERVATION_OUTPUT")


def _reject(code: str) -> NoReturn:
    raise ResearchObservationError(code)
