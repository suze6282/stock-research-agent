"""Deterministic preflight and sealing of immutable report requests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from pydantic import Field, field_validator

from stock_research_agent.domain.reports.canonical import report_checksum
from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.reports.input_verification import (
    build_report_input_manifest,
    validate_report_input_manifest,
)
from stock_research_agent.domain.reports.repositories import (
    ReportInputRepository,
    ReportRequestRepository,
)
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    FrozenReportContract,
    ReportRequestRecord,
    ReportRequestWrite,
    Version,
)
from stock_research_agent.domain.research_agent.enums import ResearchPackageStatus


class CreateReportRequest(FrozenReportContract):
    """Explicit bounded command; it contains no path, code, provider, or model input."""

    research_package_id: UUID
    report_type: ReportType
    report_locale: ReportLocale = ReportLocale.ZH_CN
    template_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    template_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    report_policy_version: Version
    reflection_policy_version: Version
    requested_sections: tuple[ReportSection, ...] = Field(min_length=1, max_length=16)
    include_evidence_appendix: bool
    include_claim_index: bool
    max_excerpt_length: int = Field(ge=1, le=1000)

    @field_validator("requested_sections")
    @classmethod
    def reject_duplicate_sections(
        cls,
        values: tuple[ReportSection, ...],
    ) -> tuple[ReportSection, ...]:
        if len(values) != len(set(values)):
            raise ValueError("requested sections must be unique")
        return values


class _IdFactory(Protocol):
    def __call__(self) -> UUID: ...


class _Clock(Protocol):
    def __call__(self) -> AwareUtcDateTime: ...


class ReportRequestError(RuntimeError):
    """Safe fixed-code report preflight failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReportRequestService:
    """Seal an exact Package and caller reductions into one immutable request."""

    def __init__(
        self,
        *,
        inputs: ReportInputRepository,
        requests: ReportRequestRepository,
        id_factory: Callable[[], UUID],
        now: Callable[[], object],
    ) -> None:
        self._inputs = inputs
        self._requests = requests
        self._id_factory = id_factory
        self._now = now

    def create(self, command: CreateReportRequest) -> ReportRequestRecord:
        report_input = self._inputs.get_package_bundle(command.research_package_id)
        if report_input is None:
            raise ReportRequestError("RESEARCH_PACKAGE_NOT_FOUND")
        manifest = build_report_input_manifest(report_input)
        verified = validate_report_input_manifest(manifest, report_input)
        self._validate_package_state(
            verified.manifest.package_status,
            command.report_type,
        )
        idempotency_basis = {
            **command.model_dump(mode="python"),
            "manifest_checksum": verified.manifest.canonical_payload_checksum,
            "package_checksum": verified.manifest.package_checksum,
            "claims_checksum": verified.manifest.claims_checksum,
            "evidence_checksum": verified.manifest.evidence_checksum,
            "links_checksum": verified.manifest.links_checksum,
            "citations_checksum": verified.manifest.citations_checksum,
            "lineage_checksum": verified.manifest.lineage_checksum,
        }
        write = ReportRequestWrite.model_validate(
            {
                **command.model_dump(mode="python", exclude={"research_package_id"}),
                "id": self._id_factory(),
                "manifest": verified.manifest,
                "idempotency_key": report_checksum(idempotency_basis),
                "created_at": self._now(),
            }
        )
        return self._requests.add_request(write)

    @staticmethod
    def _validate_package_state(
        status: ResearchPackageStatus,
        report_type: ReportType,
    ) -> None:
        if status is ResearchPackageStatus.FAILED:
            raise ReportRequestError("RESEARCH_PACKAGE_FAILED")
        if (
            status is ResearchPackageStatus.BLOCKED
            and report_type is not ReportType.DATA_QUALITY_REPORT
        ):
            raise ReportRequestError("BLOCKED_PACKAGE_REPORT_TYPE_NOT_ALLOWED")
