"""Thin read-only adapters for persisted report query projections."""

from __future__ import annotations

from pydantic import BaseModel

from stock_research_agent.domain.reports.queries import (
    ReportQueryNotFoundError,
    ReportQueryService,
)
from stock_research_agent.domain.research_agent.schemas import PageRequest
from stock_research_agent.tools.schemas_reports import (
    ReportIdInput,
    ReportPageInput,
    ReportReadOutput,
    ReportToolName,
)


class ReportReadTool:
    """Dispatch one approved read without running a report workflow."""

    def __init__(
        self,
        service: ReportQueryService,
        name: ReportToolName,
    ) -> None:
        self._service = service
        self._name = name

    def __call__(self, request: BaseModel) -> BaseModel:
        try:
            data = self._read(request)
        except ReportQueryNotFoundError:
            return ReportReadOutput(
                tool_name=self._name,
                status="BLOCKED",
                data=None,
                warnings=("REPORT_RESOURCE_NOT_FOUND",),
            )
        if isinstance(data, BaseModel):
            payload = data.model_dump(mode="json")
        elif isinstance(data, dict):
            payload = data
        else:
            raise TypeError("invalid report query projection")
        return ReportReadOutput(
            tool_name=self._name,
            status="PASS",
            data=payload,
            warnings=(),
        )

    def _read(self, request: BaseModel) -> object:
        if isinstance(request, ReportPageInput):
            page = PageRequest(limit=request.limit, offset=request.offset)
            operations = {
                "get_report_sections": self._service.list_sections,
                "get_report_blocks": self._service.list_blocks,
                "get_report_claim_bindings": (self._service.list_claim_bindings),
                "get_report_evidence_bindings": (self._service.list_evidence_bindings),
                "get_report_citations": self._service.list_citations,
                "get_report_reflection_runs": (self._service.list_reflection_runs),
                "get_report_reflection_findings": (self._service.list_reflection_findings),
                "get_report_revision_runs": self._service.list_revisions,
            }
            operation = operations.get(self._name)
            if operation is None:
                raise TypeError("invalid paged report query")
            return operation(request.report_id, page)
        if not isinstance(request, ReportIdInput):
            raise TypeError("invalid report query request")
        if self._name == "get_research_report":
            return self._service.get_report(request.report_id)
        if self._name == "get_report_release_gate":
            return self._service.get_release_gate(request.report_id)
        raise TypeError("invalid report query")


__all__ = ["ReportReadTool"]
