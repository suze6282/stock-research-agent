"""Bounded read-only projections over persisted Stage 8 report records."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from stock_research_agent.domain.research_agent.schemas import Page, PageRequest


class ReportQueryNotFoundError(LookupError):
    """Safe fixed error for a missing persisted report projection."""

    def __init__(self) -> None:
        self.code = "REPORT_RESOURCE_NOT_FOUND"
        super().__init__(self.code)


class ReportQueryRepository(Protocol):
    def get_report_view(self, report_id: UUID) -> object | None: ...

    def list_section_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]: ...

    def list_block_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]: ...

    def list_claim_binding_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]: ...

    def list_evidence_binding_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]: ...

    def list_citation_binding_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]: ...

    def list_reflection_run_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]: ...

    def list_finding_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]: ...

    def list_revision_views(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]: ...

    def get_release_gate_view(self, report_id: UUID) -> object | None: ...


class ReportQueryService:
    """Expose exactly ten reads without generation or workflow side effects."""

    def __init__(self, repository: ReportQueryRepository) -> None:
        self._repository = repository

    def get_report(self, report_id: UUID) -> object:
        return self._required(self._repository.get_report_view(report_id))

    def list_sections(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        self.get_report(report_id)
        return self._repository.list_section_views(report_id, page)

    def list_blocks(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        self.get_report(report_id)
        return self._repository.list_block_views(report_id, page)

    def list_claim_bindings(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        self.get_report(report_id)
        return self._repository.list_claim_binding_views(report_id, page)

    def list_evidence_bindings(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        self.get_report(report_id)
        return self._repository.list_evidence_binding_views(report_id, page)

    def list_citations(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        self.get_report(report_id)
        return self._repository.list_citation_binding_views(report_id, page)

    def list_reflection_runs(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        self.get_report(report_id)
        return self._repository.list_reflection_run_views(report_id, page)

    def list_reflection_findings(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        self.get_report(report_id)
        return self._repository.list_finding_views(report_id, page)

    def list_revisions(
        self,
        report_id: UUID,
        page: PageRequest,
    ) -> Page[object]:
        self.get_report(report_id)
        return self._repository.list_revision_views(report_id, page)

    def get_release_gate(self, report_id: UUID) -> object:
        self.get_report(report_id)
        return self._required(self._repository.get_release_gate_view(report_id))

    @staticmethod
    def _required(value: object | None) -> object:
        if value is None:
            raise ReportQueryNotFoundError
        return value


__all__ = [
    "ReportQueryNotFoundError",
    "ReportQueryRepository",
    "ReportQueryService",
]
