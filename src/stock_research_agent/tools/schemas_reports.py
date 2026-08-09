"""Strict schemas for the ten read-only report query tools."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

ReportToolName = Literal[
    "get_research_report",
    "get_report_sections",
    "get_report_blocks",
    "get_report_claim_bindings",
    "get_report_evidence_bindings",
    "get_report_citations",
    "get_report_reflection_runs",
    "get_report_reflection_findings",
    "get_report_revision_runs",
    "get_report_release_gate",
]


class ReportToolModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class ReportIdInput(ReportToolModel):
    report_id: UUID


class ReportPageInput(ReportIdInput):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10_000)


class ReportReadOutput(ReportToolModel):
    tool_name: ReportToolName
    tool_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["PASS", "BLOCKED"]
    data: dict[str, JsonValue] | None
    warnings: tuple[str, ...] = Field(max_length=100)


__all__ = [
    "ReportIdInput",
    "ReportPageInput",
    "ReportReadOutput",
    "ReportToolModel",
    "ReportToolName",
]
