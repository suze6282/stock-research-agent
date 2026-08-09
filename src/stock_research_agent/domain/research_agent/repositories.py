"""Persistence ports for controlled research orchestration."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkRecord,
    ClaimEvidenceLinkWrite,
    Page,
    PageRequest,
    ResearchAgentRunRecord,
    ResearchAgentRunView,
    ResearchClaimCompletion,
    ResearchClaimRecord,
    ResearchClaimView,
    ResearchClaimWrite,
    ResearchEvidenceRecord,
    ResearchEvidenceView,
    ResearchEvidenceWrite,
    ResearchObservationRecord,
    ResearchObservationWrite,
    ResearchPackageRecord,
    ResearchPackageView,
    ResearchPackageWrite,
    ResearchPlanRecord,
    ResearchPlanView,
    ResearchPlanWrite,
    ResearchPolicyRecord,
    ResearchPolicyWrite,
    ResearchRequestRecord,
    ResearchRequestWrite,
    ResearchRunEventRecord,
    ResearchRunEventView,
    ResearchRunEventWrite,
    ResearchRunUpdate,
    ResearchRunWrite,
    ResearchStepRecord,
    ResearchStepView,
    ResearchStepWrite,
    ResearchToolInvocationCompletion,
    ResearchToolInvocationRecord,
    ResearchToolInvocationView,
    ResearchToolInvocationWrite,
)


class ResearchPolicyRepository(Protocol):
    def get_policy(self, version: str) -> ResearchPolicyRecord | None: ...

    def add_policy(self, value: ResearchPolicyWrite) -> ResearchPolicyRecord: ...


class ResearchRequestRepository(Protocol):
    def add_request(self, value: ResearchRequestWrite) -> ResearchRequestRecord: ...


class ResearchRunRepository(Protocol):
    def create_run(self, value: ResearchRunWrite) -> ResearchAgentRunRecord: ...

    def get_run(
        self, run_id: UUID, *, for_update: bool = False
    ) -> ResearchAgentRunRecord | None: ...

    def find_reusable_run(self, idempotency_key: str) -> ResearchAgentRunRecord | None: ...

    def update_run(self, run_id: UUID, value: ResearchRunUpdate) -> ResearchAgentRunRecord: ...

    def append_event(self, value: ResearchRunEventWrite) -> ResearchRunEventRecord: ...


class ResearchPlanningRepository(Protocol):
    def add_plan(self, value: ResearchPlanWrite) -> ResearchPlanRecord: ...

    def add_steps(
        self, values: tuple[ResearchStepWrite, ...]
    ) -> tuple[ResearchStepRecord, ...]: ...

    def get_plan(self, run_id: UUID) -> ResearchPlanRecord | None: ...

    def list_steps(self, plan_id: UUID) -> tuple[ResearchStepRecord, ...]: ...


class ResearchExecutionRepository(Protocol):
    def add_invocation(
        self, value: ResearchToolInvocationWrite
    ) -> ResearchToolInvocationRecord: ...

    def complete_invocation(
        self,
        invocation_id: UUID,
        value: ResearchToolInvocationCompletion,
    ) -> ResearchToolInvocationRecord: ...

    def add_observation(self, value: ResearchObservationWrite) -> ResearchObservationRecord: ...


class ResearchEvidenceRepository(Protocol):
    def add_evidence(
        self, values: tuple[ResearchEvidenceWrite, ...]
    ) -> tuple[ResearchEvidenceRecord, ...]: ...

    def list_evidence(self, run_id: UUID) -> tuple[ResearchEvidenceRecord, ...]: ...


class ResearchClaimRepository(Protocol):
    def add_claim(self, value: ResearchClaimWrite) -> ResearchClaimRecord: ...

    def add_links(
        self, values: tuple[ClaimEvidenceLinkWrite, ...]
    ) -> tuple[ClaimEvidenceLinkRecord, ...]: ...

    def complete_claim(
        self,
        claim_id: UUID,
        value: ResearchClaimCompletion,
    ) -> ResearchClaimRecord: ...


class ResearchPackageRepository(Protocol):
    def add_package(self, value: ResearchPackageWrite) -> ResearchPackageRecord: ...


class ResearchQueryRepository(Protocol):
    def get_run_view(self, run_id: UUID) -> ResearchAgentRunView | None: ...

    def get_plan_view(self, run_id: UUID) -> ResearchPlanView | None: ...

    def list_step_views(self, run_id: UUID, page: PageRequest) -> Page[ResearchStepView]: ...

    def list_invocation_views(
        self, run_id: UUID, page: PageRequest
    ) -> Page[ResearchToolInvocationView]: ...

    def list_evidence_views(
        self, run_id: UUID, page: PageRequest
    ) -> Page[ResearchEvidenceView]: ...

    def list_claim_views(self, run_id: UUID, page: PageRequest) -> Page[ResearchClaimView]: ...

    def get_package_view(self, run_id: UUID) -> ResearchPackageView | None: ...

    def list_event_views(self, run_id: UUID, page: PageRequest) -> Page[ResearchRunEventView]: ...
