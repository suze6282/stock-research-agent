"""Strict immutable contracts for verifiable report inputs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from stock_research_agent.domain.documents.schemas import (
    CitationAnchorRecord,
    CitationVerification,
)
from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.research_agent.enums import (
    PackageSectionStatus,
    ResearchMode,
    ResearchPackageStatus,
    ResearchSection,
    ResearchType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ClaimEvidenceLinkRecord,
    ResearchAgentRunRecord,
    ResearchClaimRecord,
    ResearchEvidenceRecord,
    ResearchPackageRecord,
    ResearchRequestRecord,
)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("datetime must be timezone-aware UTC")
    return value.astimezone(UTC)


AwareUtcDateTime = Annotated[datetime, AfterValidator(_aware_utc)]
Checksum = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Version = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,127}$")]
Code = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_:-]{0,127}$")]


class FrozenReportContract(BaseModel):
    """Reject unknown input and prevent mutation after validation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class ReportInputIssue(FrozenReportContract):
    """Stable data-quality or limitation item captured from the research package."""

    code: Code
    claim_id: UUID | None = None
    evidence_id: UUID | None = None
    citation_id: UUID | None = None


class ReportInputSectionState(FrozenReportContract):
    """Exact Stage 7 Package section state sealed into the Manifest."""

    section: ResearchSection
    status: PackageSectionStatus
    claim_ids: tuple[UUID, ...] = Field(max_length=100)
    warning_codes: tuple[Code, ...] = Field(max_length=100)


def _issue_key(issue: ReportInputIssue) -> tuple[str, str, str, str]:
    return (
        issue.code,
        str(issue.claim_id or ""),
        str(issue.evidence_id or ""),
        str(issue.citation_id or ""),
    )


class ReportInputManifest(FrozenReportContract):
    """Exact immutable point-in-time input contract for one report build."""

    research_package_id: UUID
    research_agent_run_id: UUID
    research_request_id: UUID
    security_id: UUID
    issuer_id: UUID
    snapshot_id: UUID
    research_as_of_time: AwareUtcDateTime
    research_type: ResearchType
    research_mode: ResearchMode
    package_status: ResearchPackageStatus
    package_checksum: Checksum
    policy_version: Version
    planner_version: Version
    tool_catalog_version: str = Field(min_length=80, max_length=80)
    evidence_version: Version
    claim_version: Version
    package_version: Version
    claim_ids: tuple[UUID, ...] = Field(max_length=500)
    evidence_ids: tuple[UUID, ...] = Field(max_length=1000)
    link_ids: tuple[UUID, ...] = Field(max_length=5000)
    citation_ids: tuple[UUID, ...] = Field(max_length=1000)
    lineage_ids: tuple[UUID, ...] = Field(max_length=5000)
    claims_checksum: Checksum
    evidence_checksum: Checksum
    links_checksum: Checksum
    citations_checksum: Checksum
    lineage_checksum: Checksum
    section_states: tuple[ReportInputSectionState, ...] = Field(
        min_length=1,
        max_length=10,
    )
    blocked_capabilities: tuple[Code, ...] = Field(max_length=100)
    warnings: tuple[Code, ...] = Field(max_length=100)
    data_quality_items: tuple[ReportInputIssue, ...] = Field(max_length=500)
    limitation_items: tuple[ReportInputIssue, ...] = Field(max_length=500)
    synthetic_status: SyntheticStatus
    manifest_schema_version: str = Field(pattern=r"^report-input-manifest-v[1-9][0-9]*$")
    canonical_payload_checksum: Checksum
    created_at: AwareUtcDateTime

    @field_validator(
        "claim_ids",
        "evidence_ids",
        "link_ids",
        "citation_ids",
        "lineage_ids",
    )
    @classmethod
    def require_stable_sorted_unique_ids(
        cls,
        values: tuple[UUID, ...],
    ) -> tuple[UUID, ...]:
        if values != tuple(sorted(set(values), key=str)):
            raise ValueError("record ids must be stable sorted unique")
        return values

    @field_validator("blocked_capabilities", "warnings")
    @classmethod
    def require_stable_sorted_unique_codes(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))):
            raise ValueError("codes must be stable sorted unique")
        return values

    @field_validator("data_quality_items", "limitation_items")
    @classmethod
    def require_stable_sorted_unique_issues(
        cls,
        values: tuple[ReportInputIssue, ...],
    ) -> tuple[ReportInputIssue, ...]:
        keys = tuple(_issue_key(issue) for issue in values)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("issues must be stable sorted unique")
        return values


class PersistedReportInput(FrozenReportContract):
    """Exact Stage 7 records loaded for one report manifest."""

    package: ResearchPackageRecord
    run: ResearchAgentRunRecord
    request: ResearchRequestRecord
    issuer_id: UUID
    claims: tuple[ResearchClaimRecord, ...] = Field(max_length=500)
    evidence: tuple[ResearchEvidenceRecord, ...] = Field(max_length=1000)
    links: tuple[ClaimEvidenceLinkRecord, ...] = Field(max_length=5000)
    citations: tuple[CitationAnchorRecord, ...] = Field(max_length=1000)
    citation_verifications: tuple[CitationVerification, ...] = Field(max_length=1000)


class VerifiedReportInput(FrozenReportContract):
    """A persisted input bundle proven to match its sealed manifest."""

    manifest: ReportInputManifest
    input: PersistedReportInput


class ReportRequestWrite(FrozenReportContract):
    """Immutable report request ready for transaction-owned persistence."""

    id: UUID
    manifest: ReportInputManifest
    report_type: ReportType
    report_locale: ReportLocale
    template_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    template_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    report_policy_version: Version
    reflection_policy_version: Version
    requested_sections: tuple[ReportSection, ...] = Field(min_length=1, max_length=16)
    include_evidence_appendix: bool
    include_claim_index: bool
    max_excerpt_length: int = Field(ge=1, le=1000)
    idempotency_key: Checksum
    created_at: AwareUtcDateTime


class ReportRequestRecord(ReportRequestWrite):
    """Persisted immutable report request."""


class ReportPolicyRecord(FrozenReportContract):
    """Versioned deterministic report-generation permission contract."""

    version: Version
    checksum: Checksum
    allowed_report_types: tuple[ReportType, ...] = Field(min_length=1, max_length=4)
    allowed_locales: tuple[ReportLocale, ...] = Field(min_length=1, max_length=2)
    allowed_sections: tuple[ReportSection, ...] = Field(min_length=1, max_length=16)
    include_unsupported_claims: Literal[True]
    include_conflicting_claims: Literal[True]
    include_blocked_capabilities: Literal[True]
    include_data_quality: Literal[True]
    include_limitations: Literal[True]
    require_claim_binding: Literal[True]
    require_evidence_binding: Literal[True]
    require_valid_document_citation: Literal[True]
    allow_synthetic_evidence: Literal[False]
    allow_unknown_published_at: Literal[False]
    max_report_blocks: int = Field(ge=1, le=300)
    max_claims_per_block: int = Field(ge=1, le=20)
    max_citations_per_block: int = Field(ge=1, le=20)
    max_excerpt_length: int = Field(ge=1, le=1000)
    max_reflection_rounds: int = Field(ge=1, le=2)
    max_revision_rounds: int = Field(ge=0, le=1)
    allow_model_narrative: Literal[False]
    allow_model_reflection: Literal[False]


class ReportPolicyWrite(ReportPolicyRecord):
    """Policy value accepted by the transaction-neutral repository."""


class ReportPolicySeedResult(FrozenReportContract):
    policy: ReportPolicyRecord
    created: bool
