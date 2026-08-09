"""Strict schemas for the eight read-only Research Agent query tools."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class ResearchAgentToolModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class ResearchRunIdInput(ResearchAgentToolModel):
    run_id: UUID


class ResearchRunPageInput(ResearchRunIdInput):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10_000)


class GetResearchAgentRunOutput(ResearchAgentToolModel):
    tool_name: Literal["get_research_agent_run"] = "get_research_agent_run"
    tool_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["PASS", "BLOCKED"]
    data: dict[str, JsonValue] | None
    warnings: tuple[str, ...] = Field(max_length=100)


class GetResearchPlanOutput(ResearchAgentToolModel):
    tool_name: Literal["get_research_plan"] = "get_research_plan"
    tool_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["PASS", "BLOCKED"]
    data: dict[str, JsonValue] | None
    warnings: tuple[str, ...] = Field(max_length=100)


class GetResearchStepsOutput(ResearchAgentToolModel):
    tool_name: Literal["get_research_steps"] = "get_research_steps"
    tool_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["PASS", "BLOCKED"]
    data: dict[str, JsonValue] | None
    warnings: tuple[str, ...] = Field(max_length=100)


class GetResearchToolInvocationsOutput(ResearchAgentToolModel):
    tool_name: Literal["get_research_tool_invocations"] = "get_research_tool_invocations"
    tool_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["PASS", "BLOCKED"]
    data: dict[str, JsonValue] | None
    warnings: tuple[str, ...] = Field(max_length=100)


class GetResearchEvidenceOutput(ResearchAgentToolModel):
    tool_name: Literal["get_research_evidence"] = "get_research_evidence"
    tool_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["PASS", "BLOCKED"]
    data: dict[str, JsonValue] | None
    warnings: tuple[str, ...] = Field(max_length=100)


class GetResearchClaimsOutput(ResearchAgentToolModel):
    tool_name: Literal["get_research_claims"] = "get_research_claims"
    tool_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["PASS", "BLOCKED"]
    data: dict[str, JsonValue] | None
    warnings: tuple[str, ...] = Field(max_length=100)


class GetResearchPackageOutput(ResearchAgentToolModel):
    tool_name: Literal["get_research_package"] = "get_research_package"
    tool_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["PASS", "BLOCKED"]
    data: dict[str, JsonValue] | None
    warnings: tuple[str, ...] = Field(max_length=100)


class GetResearchRunEventsOutput(ResearchAgentToolModel):
    tool_name: Literal["get_research_run_events"] = "get_research_run_events"
    tool_version: Literal["1.0.0"] = "1.0.0"
    status: Literal["PASS", "BLOCKED"]
    data: dict[str, JsonValue] | None
    warnings: tuple[str, ...] = Field(max_length=100)


__all__ = [
    "GetResearchAgentRunOutput",
    "GetResearchClaimsOutput",
    "GetResearchEvidenceOutput",
    "GetResearchPackageOutput",
    "GetResearchPlanOutput",
    "GetResearchRunEventsOutput",
    "GetResearchStepsOutput",
    "GetResearchToolInvocationsOutput",
    "ResearchRunIdInput",
    "ResearchRunPageInput",
]
