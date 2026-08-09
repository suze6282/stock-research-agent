"""Persistence ports for verifiable report inputs and requests."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from stock_research_agent.domain.reports.bindings import (
    ReportCitationBindingWrite,
    ReportClaimBindingWrite,
    ReportEvidenceBindingWrite,
)
from stock_research_agent.domain.reports.enums import ReportLocale
from stock_research_agent.domain.reports.generation import (
    ReportGenerationRunRecord,
    ReportGenerationRunWrite,
    ReportGenerationTransition,
)
from stock_research_agent.domain.reports.reflection import (
    ReportReflectionCompletion,
    ReportReflectionFindingWrite,
    ReportReflectionResult,
    ReportReflectionRunRecord,
    ReportReflectionRunWrite,
)
from stock_research_agent.domain.reports.release_gate import (
    ReportReleaseGateRecord,
    ReportReleaseGateWrite,
)
from stock_research_agent.domain.reports.reporting import (
    ResearchReportAggregate,
    ResearchReportAggregateWrite,
    ResearchReportRecord,
)
from stock_research_agent.domain.reports.revision import (
    ReportRevisionCompletion,
    ReportRevisionResult,
    ReportRevisionRunRecord,
    ReportRevisionRunWrite,
)
from stock_research_agent.domain.reports.schemas import (
    PersistedReportInput,
    ReportPolicyRecord,
    ReportPolicyWrite,
    ReportRequestRecord,
    ReportRequestWrite,
)
from stock_research_agent.domain.reports.templates import (
    ReportTemplateVersionRecord,
    ReportTemplateVersionWrite,
)


@runtime_checkable
class ReportInputRepository(Protocol):
    def get_package_bundle(
        self,
        research_package_id: UUID,
    ) -> PersistedReportInput | None: ...


@runtime_checkable
class ReportRequestRepository(Protocol):
    def add_request(self, value: ReportRequestWrite) -> ReportRequestRecord: ...

    def get_request(self, request_id: UUID) -> ReportRequestRecord | None: ...


@runtime_checkable
class ReportPolicyRepository(Protocol):
    def get_policy(self, version: str) -> ReportPolicyRecord | None: ...

    def add_policy(self, value: ReportPolicyWrite) -> ReportPolicyRecord: ...


@runtime_checkable
class ReportTemplateRepository(Protocol):
    def get_template(
        self,
        name: str,
        version: str,
        locale: ReportLocale,
    ) -> ReportTemplateVersionRecord | None: ...

    def add_template(
        self,
        value: ReportTemplateVersionWrite,
    ) -> ReportTemplateVersionRecord: ...


@runtime_checkable
class ReportGenerationRepository(Protocol):
    def create_run(
        self,
        value: ReportGenerationRunWrite,
    ) -> ReportGenerationRunRecord: ...

    def get_run(
        self,
        run_id: UUID,
        *,
        for_update: bool = False,
    ) -> ReportGenerationRunRecord | None: ...

    def find_reusable_run(
        self,
        idempotency_key: str,
    ) -> ReportGenerationRunRecord | None: ...

    def transition(
        self,
        run_id: UUID,
        value: ReportGenerationTransition,
    ) -> ReportGenerationRunRecord: ...


@runtime_checkable
class ResearchReportRepository(Protocol):
    def add_report(
        self,
        value: ResearchReportAggregateWrite,
    ) -> ResearchReportAggregate: ...

    def get_report(self, report_id: UUID) -> ResearchReportAggregate | None: ...

    def list_versions(
        self,
        generation_run_id: UUID,
    ) -> tuple[ResearchReportRecord, ...]: ...

    def add_bindings(
        self,
        report_id: UUID,
        claim_bindings: tuple[ReportClaimBindingWrite, ...],
        evidence_bindings: tuple[ReportEvidenceBindingWrite, ...],
        citation_bindings: tuple[ReportCitationBindingWrite, ...],
    ) -> None: ...


@runtime_checkable
class ReportReflectionRepository(Protocol):
    def create_run(
        self,
        value: ReportReflectionRunWrite,
    ) -> ReportReflectionRunRecord: ...

    def get_result(self, run_id: UUID) -> ReportReflectionResult | None: ...

    def complete_run(
        self,
        run_id: UUID,
        result: ReportReflectionCompletion,
        findings: tuple[ReportReflectionFindingWrite, ...],
    ) -> ReportReflectionResult: ...


@runtime_checkable
class ReportRevisionRepository(Protocol):
    def create_run(
        self,
        value: ReportRevisionRunWrite,
    ) -> ReportRevisionRunRecord: ...

    def complete_run(
        self,
        run_id: UUID,
        result: ReportRevisionCompletion,
        target: ResearchReportAggregateWrite | None,
    ) -> ReportRevisionResult: ...


@runtime_checkable
class ReportReleaseGateRepository(Protocol):
    def add_gate(
        self,
        value: ReportReleaseGateWrite,
    ) -> ReportReleaseGateRecord: ...
