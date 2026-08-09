"""Thin read-only adapters for persisted Research Agent query projections."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from stock_research_agent.domain.research_agent.queries import (
    ResearchAgentQueryService,
    ResearchQueryNotFoundError,
)
from stock_research_agent.domain.research_agent.schemas import PageRequest
from stock_research_agent.tools.schemas_research_agent import (
    GetResearchAgentRunOutput,
    GetResearchClaimsOutput,
    GetResearchEvidenceOutput,
    GetResearchPackageOutput,
    GetResearchPlanOutput,
    GetResearchRunEventsOutput,
    GetResearchStepsOutput,
    GetResearchToolInvocationsOutput,
    ResearchRunIdInput,
    ResearchRunPageInput,
)

OutputFactory = Callable[..., BaseModel]


class ResearchAgentReadTool:
    """Dispatch one approved query without invoking another Tool or any write."""

    def __init__(self, service: ResearchAgentQueryService, name: str) -> None:
        self._service = service
        self._name = name

    def __call__(self, request: BaseModel) -> BaseModel:
        try:
            data = self._read(request)
        except ResearchQueryNotFoundError:
            return self._output(
                status="BLOCKED",
                data=None,
                warnings=("RESEARCH_RESOURCE_NOT_FOUND",),
            )
        return self._output(status="PASS", data=data, warnings=())

    def _read(self, request: BaseModel) -> object:
        if isinstance(request, ResearchRunPageInput):
            self._service.get_run(request.run_id)
            page = PageRequest(limit=request.limit, offset=request.offset)
            if self._name == "get_research_steps":
                return self._service.list_steps(request.run_id, page)
            if self._name == "get_research_tool_invocations":
                return self._service.list_invocations(request.run_id, page)
            if self._name == "get_research_evidence":
                return self._service.list_evidence(request.run_id, page)
            if self._name == "get_research_claims":
                return self._service.list_claims(request.run_id, page)
            if self._name == "get_research_run_events":
                return self._service.list_events(request.run_id, page)
            raise TypeError("invalid paged Research Agent query")
        if not isinstance(request, ResearchRunIdInput):
            raise TypeError("invalid Research Agent query request")
        if self._name == "get_research_agent_run":
            return self._service.get_run(request.run_id)
        if self._name == "get_research_plan":
            return self._service.get_plan(request.run_id)
        if self._name == "get_research_package":
            return self._service.get_package(request.run_id)
        raise TypeError("invalid Research Agent query")

    def _output(self, **values: object) -> BaseModel:
        data = values.get("data")
        if isinstance(data, BaseModel):
            values["data"] = data.model_dump(mode="json")
        output_models: dict[str, OutputFactory] = {
            "get_research_agent_run": GetResearchAgentRunOutput,
            "get_research_plan": GetResearchPlanOutput,
            "get_research_steps": GetResearchStepsOutput,
            "get_research_tool_invocations": GetResearchToolInvocationsOutput,
            "get_research_evidence": GetResearchEvidenceOutput,
            "get_research_claims": GetResearchClaimsOutput,
            "get_research_package": GetResearchPackageOutput,
            "get_research_run_events": GetResearchRunEventsOutput,
        }
        return output_models[self._name](**values)


__all__ = ["ResearchAgentReadTool"]
