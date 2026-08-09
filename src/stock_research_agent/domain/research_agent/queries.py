"""Bounded read-only projections over persisted Research Agent runs."""

from __future__ import annotations

from uuid import UUID

from stock_research_agent.domain.research_agent.repositories import (
    ResearchQueryRepository,
)
from stock_research_agent.domain.research_agent.schemas import (
    Page,
    PageRequest,
    ResearchAgentRunView,
    ResearchClaimView,
    ResearchEvidenceView,
    ResearchPackageView,
    ResearchPlanView,
    ResearchRunEventView,
    ResearchStepView,
    ResearchToolInvocationView,
)


class ResearchQueryNotFoundError(LookupError):
    """A fixed safe error that does not reveal persistence details."""

    def __init__(self) -> None:
        self.code = "RESEARCH_RESOURCE_NOT_FOUND"
        super().__init__(self.code)


class ResearchAgentQueryService:
    """Expose exactly eight bounded reads and perform no persistence writes."""

    def __init__(self, repository: ResearchQueryRepository) -> None:
        self._repository = repository

    def get_run(self, run_id: UUID) -> ResearchAgentRunView:
        return self._required(self._repository.get_run_view(run_id))

    def get_plan(self, run_id: UUID) -> ResearchPlanView:
        return self._required(self._repository.get_plan_view(run_id))

    def list_steps(
        self,
        run_id: UUID,
        page: PageRequest,
    ) -> Page[ResearchStepView]:
        return self._repository.list_step_views(run_id, page)

    def list_invocations(
        self,
        run_id: UUID,
        page: PageRequest,
    ) -> Page[ResearchToolInvocationView]:
        return self._repository.list_invocation_views(run_id, page)

    def list_evidence(
        self,
        run_id: UUID,
        page: PageRequest,
    ) -> Page[ResearchEvidenceView]:
        return self._repository.list_evidence_views(run_id, page)

    def list_claims(
        self,
        run_id: UUID,
        page: PageRequest,
    ) -> Page[ResearchClaimView]:
        return self._repository.list_claim_views(run_id, page)

    def get_package(self, run_id: UUID) -> ResearchPackageView:
        return self._required(self._repository.get_package_view(run_id))

    def list_events(
        self,
        run_id: UUID,
        page: PageRequest,
    ) -> Page[ResearchRunEventView]:
        return self._repository.list_event_views(run_id, page)

    @staticmethod
    def _required[ViewT](value: ViewT | None) -> ViewT:
        if value is None:
            raise ResearchQueryNotFoundError
        return value
