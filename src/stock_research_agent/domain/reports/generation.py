"""Finite immutable lifecycle contracts for report generation runs."""

from __future__ import annotations

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from stock_research_agent.domain.reports.enums import ReportLocale, ReportType
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    Checksum,
    Code,
    FrozenReportContract,
    Version,
)


class ReportGenerationStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


TERMINAL_GENERATION_STATUSES = frozenset(
    {
        ReportGenerationStatus.COMPLETED,
        ReportGenerationStatus.PARTIAL,
        ReportGenerationStatus.BLOCKED,
        ReportGenerationStatus.FAILED,
    }
)


class ReportGenerationRunWrite(FrozenReportContract):
    id: UUID
    report_request_id: UUID
    research_package_id: UUID
    research_agent_run_id: UUID
    security_id: UUID
    snapshot_id: UUID
    research_as_of_time: AwareUtcDateTime
    report_type: ReportType
    report_locale: ReportLocale
    report_policy_version: Version
    template_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    template_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    renderer_version: Version
    manifest_schema_version: Version
    manifest_checksum: Checksum
    package_checksum: Checksum
    claims_checksum: Checksum
    evidence_checksum: Checksum
    links_checksum: Checksum
    citations_checksum: Checksum
    lineage_checksum: Checksum
    idempotency_key: Checksum
    status: ReportGenerationStatus
    warning_count: int = Field(ge=0, le=1000)
    blocked_reason_code: Code | None = None
    error_code: Code | None = None
    safe_error_message: str | None = Field(default=None, max_length=256)
    created_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    terminal_at: AwareUtcDateTime | None = None


class ReportGenerationRunRecord(ReportGenerationRunWrite):
    pass


class ReportGenerationTransition(FrozenReportContract):
    expected_status: ReportGenerationStatus
    target_status: ReportGenerationStatus
    warning_count: int = Field(ge=0, le=1000)
    blocked_reason_code: Code | None = None
    error_code: Code | None = None
    safe_error_message: str | None = Field(default=None, max_length=256)
    changed_at: AwareUtcDateTime

    @model_validator(mode="after")
    def require_transition_result_shape(self) -> Self:
        ReportGenerationStateMachine().transition(self.expected_status, self.target_status)
        if self.target_status is ReportGenerationStatus.RUNNING:
            if (
                self.warning_count != 0
                or self.blocked_reason_code is not None
                or self.error_code is not None
                or self.safe_error_message is not None
            ):
                raise ValueError("running transition cannot carry terminal result fields")
            return self
        if self.target_status is ReportGenerationStatus.FAILED and (
            self.error_code is None or self.safe_error_message is None
        ):
            raise ValueError("failed terminal transition requires safe error")
        if self.target_status is not ReportGenerationStatus.FAILED and (
            self.error_code is not None or self.safe_error_message is not None
        ):
            raise ValueError("non-failed terminal transition cannot carry error")
        if (
            self.target_status in {ReportGenerationStatus.PARTIAL, ReportGenerationStatus.BLOCKED}
            and self.blocked_reason_code is None
        ):
            raise ValueError("partial or blocked terminal transition requires reason")
        return self


class ReportGenerationTransitionError(RuntimeError):
    pass


class ReportGenerationStateMachine:
    def transition(
        self,
        current: ReportGenerationStatus,
        target: ReportGenerationStatus,
    ) -> ReportGenerationStatus:
        allowed = (
            current is ReportGenerationStatus.CREATED and target is ReportGenerationStatus.RUNNING
        ) or (current is ReportGenerationStatus.RUNNING and target in TERMINAL_GENERATION_STATUSES)
        if not allowed:
            raise ReportGenerationTransitionError(
                f"REPORT_GENERATION_TRANSITION_FORBIDDEN:{current.value}:{target.value}"
            )
        return target
