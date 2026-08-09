"""Immutable persistence contracts for report lineage bindings."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from stock_research_agent.domain.documents.enums import CitationStatus
from stock_research_agent.domain.reports.schemas import (
    AwareUtcDateTime,
    FrozenReportContract,
)
from stock_research_agent.domain.research_agent.enums import EvidenceRole


class ReportClaimBindingRole(StrEnum):
    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    LIMITATION = "LIMITATION"


class ReportClaimBindingWrite(FrozenReportContract):
    id: UUID
    report_block_id: UUID
    claim_id: UUID
    role: ReportClaimBindingRole
    sentence_index: int | None = Field(default=None, ge=0, le=999)
    item_or_row_key: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9_.-]{0,127}$",
    )
    created_at: AwareUtcDateTime


class VisibleReferenceKind(StrEnum):
    EVIDENCE = "EVIDENCE"
    METRIC = "METRIC"


class ReportEvidenceBindingWrite(FrozenReportContract):
    id: UUID
    report_block_id: UUID
    report_claim_binding_id: UUID
    claim_evidence_link_id: UUID
    evidence_id: UUID
    role: EvidenceRole
    visible_reference_kind: VisibleReferenceKind
    visible_reference: str = Field(pattern=r"^(EV|MET)-[0-9]{3}$")
    item_or_row_key: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,127}$")
    citation_id: UUID | None = None
    source_record_id: UUID | None = None
    source_checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    created_at: AwareUtcDateTime

    @model_validator(mode="after")
    def require_reference_prefix(self) -> Self:
        prefix = "MET-" if self.visible_reference_kind is VisibleReferenceKind.METRIC else "EV-"
        if not self.visible_reference.startswith(prefix):
            raise ValueError("visible reference prefix does not match its kind")
        return self


class ReportCitationBindingWrite(FrozenReportContract):
    id: UUID
    report_evidence_binding_id: UUID
    citation_id: UUID
    document_version_id: UUID
    visible_reference: str = Field(pattern=r"^CIT-[0-9]{3}$")
    locator_summary: str = Field(min_length=1, max_length=1000)
    rendered_excerpt: str = Field(min_length=1, max_length=1000)
    rendered_excerpt_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    citation_status: Literal[CitationStatus.VALID]
    created_at: AwareUtcDateTime


__all__ = [
    "ReportCitationBindingWrite",
    "ReportClaimBindingRole",
    "ReportClaimBindingWrite",
    "ReportEvidenceBindingWrite",
    "VisibleReferenceKind",
]
