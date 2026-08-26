"""Read-only adapters for persisted controlled-evidence projections."""

from __future__ import annotations

from pydantic import BaseModel

from stock_research_agent.domain.live_evidence.queries import LiveEvidenceQueryService

from .schemas_live_evidence import (
    LiveEvidenceReadOutput,
    LiveEvidenceResourceInput,
    LiveEvidenceToolName,
)


class LiveEvidenceReadTool:
    def __init__(self, service: LiveEvidenceQueryService, name: LiveEvidenceToolName) -> None:
        self._service = service
        self._name = name

    def __call__(self, request: BaseModel) -> BaseModel:
        if not isinstance(request, LiveEvidenceResourceInput):
            raise TypeError("invalid controlled-evidence query")
        data = self._service.query(
            self._name,
            request.resource_id,
            limit=request.limit,
            offset=request.offset,
        )
        return LiveEvidenceReadOutput(
            tool_name=self._name,
            status="BLOCKED" if data is None else "PASS",
            data=data,
            warnings=("RESOURCE_NOT_FOUND",) if data is None else (),
        )
