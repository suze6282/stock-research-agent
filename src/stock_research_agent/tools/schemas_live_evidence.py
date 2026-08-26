"""Strict schemas for ten read-only controlled-evidence query tools."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

LiveEvidenceToolName = Literal[
    "get_live_authorization",
    "list_live_authorization_events",
    "list_live_authorization_consumptions",
    "get_live_execution_approval",
    "get_manual_evidence_import",
    "get_evidence_ingestion_manifest",
    "get_real_company_validation_run",
    "list_end_to_end_validations",
    "get_live_incident",
    "list_live_incident_events",
]


class LiveEvidenceToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class LiveEvidenceResourceInput(LiveEvidenceToolModel):
    resource_id: UUID
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100_000)


class LiveEvidenceReadOutput(LiveEvidenceToolModel):
    tool_name: LiveEvidenceToolName
    tool_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["PASS", "BLOCKED"]
    data: dict[str, JsonValue] | None
    warnings: tuple[str, ...] = Field(max_length=100)
