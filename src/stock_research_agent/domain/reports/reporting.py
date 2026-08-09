"""Immutable canonical structured research report contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Self
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, JsonValue, field_validator, model_validator

from stock_research_agent.domain.reports.binding_schemas import (
    ReportCitationBindingWrite,
    ReportClaimBindingRole,
    ReportClaimBindingWrite,
    ReportEvidenceBindingWrite,
)
from stock_research_agent.domain.reports.enums import (
    ReportLocale,
    ReportSection,
    ReportType,
)
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenReportContract,
    Version,
)


class ResearchReportStatus(StrEnum):
    DRAFT = "DRAFT"
    REFLECTED = "REFLECTED"
    REVISED = "REVISED"
    PUBLISHABLE = "PUBLISHABLE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class ReportSectionStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NO_EVIDENCE = "NO_EVIDENCE"
    NOT_REQUESTED = "NOT_REQUESTED"


class ReportBlockType(StrEnum):
    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    BULLET_LIST = "BULLET_LIST"
    METRIC_TABLE = "METRIC_TABLE"
    EVIDENCE_TABLE = "EVIDENCE_TABLE"
    WARNING = "WARNING"
    LIMITATION = "LIMITATION"
    CONFLICT = "CONFLICT"
    CLAIM_INDEX = "CLAIM_INDEX"
    CITATION_LIST = "CITATION_LIST"


class ReportBlockStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NO_EVIDENCE = "NO_EVIDENCE"
    NOT_REQUESTED = "NOT_REQUESTED"


class StructuredReportBlock(FrozenReportContract):
    block_key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,127}$")
    block_index: int = Field(ge=0, le=299)
    block_type: ReportBlockType
    status: ReportBlockStatus
    text: str | None = Field(default=None, max_length=10_000)
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class StructuredReportSection(FrozenReportContract):
    section: ReportSection
    section_index: int = Field(ge=0, le=15)
    title: str = Field(min_length=1, max_length=160)
    status: ReportSectionStatus
    blocks: tuple[StructuredReportBlock, ...] = Field(max_length=300)

    @model_validator(mode="after")
    def require_contiguous_block_indices(self) -> Self:
        if tuple(item.block_index for item in self.blocks) != tuple(range(len(self.blocks))):
            raise ValueError("block indices must be contiguous")
        if len({item.block_key for item in self.blocks}) != len(self.blocks):
            raise ValueError("block keys must be unique within a section")
        return self


class StructuredReportContent(FrozenReportContract):
    schema_version: str = Field(pattern=r"^research-report-v[1-9][0-9]*$")
    locale: ReportLocale
    sections: tuple[StructuredReportSection, ...] = Field(
        min_length=1,
        max_length=16,
    )

    @model_validator(mode="after")
    def require_bounded_contiguous_sections(self) -> Self:
        if tuple(item.section_index for item in self.sections) != tuple(range(len(self.sections))):
            raise ValueError("section indices must be contiguous")
        if len({item.section for item in self.sections}) != len(self.sections):
            raise ValueError("section keys must be unique")
        if sum(len(item.blocks) for item in self.sections) > 300:
            raise ValueError("report blocks exceed approved bound")
        return self


class ResearchReportRecord(FrozenReportContract):
    id: UUID
    report_generation_run_id: UUID
    report_version: int = Field(ge=1)
    previous_report_id: UUID | None = None
    report_type: ReportType
    report_locale: ReportLocale
    status: ResearchReportStatus
    title: str = Field(min_length=1, max_length=256)
    subtitle: str | None = Field(default=None, max_length=512)
    security_id: UUID
    snapshot_id: UUID
    research_as_of_time: AwareUtcDateTime
    research_package_id: UUID
    input_manifest_checksum: Checksum
    package_checksum: Checksum
    structured_content: StructuredReportContent
    markdown_content: str = Field(min_length=1, max_length=1_048_576)
    structured_checksum: Checksum
    markdown_checksum: Checksum
    content_checksum: Checksum
    claim_set_checksum: Checksum
    evidence_set_checksum: Checksum
    link_set_checksum: Checksum
    citation_set_checksum: Checksum
    renderer_version: Version
    template_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    template_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    created_at: AwareUtcDateTime

    @field_validator("markdown_content")
    @classmethod
    def require_canonical_markdown(cls, value: str) -> str:
        if "\r" in value or not value.endswith("\n"):
            raise ValueError("Markdown must use LF and one trailing newline")
        if value.endswith("\n\n"):
            raise ValueError("Markdown must use LF and one trailing newline")
        return value


class ResearchReportAggregateWrite(FrozenReportContract):
    report: ResearchReportRecord
    claim_bindings: tuple[ReportClaimBindingWrite, ...] = Field(
        default=(),
        max_length=5000,
    )
    evidence_bindings: tuple[ReportEvidenceBindingWrite, ...] = Field(
        default=(),
        max_length=5000,
    )
    citation_bindings: tuple[ReportCitationBindingWrite, ...] = Field(
        default=(),
        max_length=1000,
    )

    @model_validator(mode="after")
    def require_complete_binding_graph(self) -> Self:
        block_ids = {
            uuid5(
                NAMESPACE_URL,
                f"{self.report.id}:block:{block.block_key}",
            ): block
            for section in self.report.structured_content.sections
            for block in section.blocks
        }
        factual_ids = {
            block_id
            for block_id, block in block_ids.items()
            if block.block_type in {ReportBlockType.METRIC_TABLE, ReportBlockType.CONFLICT}
            or any(key in block.payload for key in ("claim_id", "statement_code", "support_status"))
        }
        if not self.claim_bindings:
            return self
        claim_by_id = {value.id: value for value in self.claim_bindings}
        if len(claim_by_id) != len(self.claim_bindings):
            raise ValueError("report claim binding ids must be unique")
        if {value.report_block_id for value in self.claim_bindings} - block_ids.keys():
            raise ValueError("claim binding references an unknown report block")
        bound_factual_ids = {value.report_block_id for value in self.claim_bindings}
        if factual_ids != bound_factual_ids:
            raise ValueError("every factual report block requires an exact claim binding")
        evidence_by_id = {value.id: value for value in self.evidence_bindings}
        if len(evidence_by_id) != len(self.evidence_bindings):
            raise ValueError("report evidence binding ids must be unique")
        for value in self.evidence_bindings:
            claim = claim_by_id.get(value.report_claim_binding_id)
            if claim is None or claim.report_block_id != value.report_block_id:
                raise ValueError("evidence binding claim/block context mismatch")
        claims_requiring_evidence = {
            value.id
            for value in self.claim_bindings
            if value.role is not ReportClaimBindingRole.LIMITATION
        }
        if claims_requiring_evidence - {
            value.report_claim_binding_id for value in self.evidence_bindings
        }:
            raise ValueError("supported report claim binding requires evidence")
        if any(
            value.report_evidence_binding_id not in evidence_by_id
            for value in self.citation_bindings
        ):
            raise ValueError("citation binding references unknown report evidence binding")
        return self


class ResearchReportAggregate(ResearchReportAggregateWrite):
    pass
