"""Point-in-time Evidence Ledger admission rules."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from stock_research_agent.domain.research_agent.enums import (
    EvidenceStatus,
    EvidenceType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ControlledRunContext,
    ResearchEvidenceWrite,
    ResearchObservationRecord,
)


class EvidenceSource(BaseModel):
    """Already-loaded source ancestry supplied by a repository adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record_type: str = Field(min_length=1, max_length=128)
    record_id: UUID
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    exists: bool
    security_id: UUID
    snapshot_id: UUID
    published_at: datetime | None
    citation_id: UUID | None
    citation_valid: bool | None
    calculation_run_id: UUID | None
    calculation_input_ids: tuple[UUID, ...] = Field(max_length=100)
    formula_version: str | None = Field(default=None, max_length=128)
    metric_lineage_valid: bool | None
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class EvidenceLedgerService:
    """Admit every result for audit while assigning eligibility deterministically."""

    def admit(
        self,
        *,
        evidence_id: UUID,
        context: ControlledRunContext,
        observation: ResearchObservationRecord,
        evidence_type: EvidenceType,
        source: EvidenceSource,
        synthetic_status: SyntheticStatus,
        real_research: bool,
        created_at: datetime,
    ) -> ResearchEvidenceWrite:
        status, warnings = self._classify(
            context=context,
            observation=observation,
            evidence_type=evidence_type,
            source=source,
            synthetic_status=synthetic_status,
            real_research=real_research,
        )
        return ResearchEvidenceWrite(
            id=evidence_id,
            run_id=context.research_agent_run_id,
            observation_id=observation.id,
            evidence_type=evidence_type,
            status=status,
            schema_version="evidence-v1",
            security_id=context.security_id,
            snapshot_id=context.snapshot_id,
            research_as_of_time=context.research_as_of_time,
            source_record_type=source.record_type,
            source_record_id=source.record_id,
            source_checksum=source.checksum,
            published_at=source.published_at,
            citation_id=source.citation_id,
            calculation_run_id=source.calculation_run_id,
            calculation_input_ids=source.calculation_input_ids,
            formula_version=source.formula_version,
            synthetic_status=synthetic_status,
            payload=source.payload,
            warning_codes=warnings,
            created_at=created_at,
        )

    @staticmethod
    def _classify(
        *,
        context: ControlledRunContext,
        observation: ResearchObservationRecord,
        evidence_type: EvidenceType,
        source: EvidenceSource,
        synthetic_status: SyntheticStatus,
        real_research: bool,
    ) -> tuple[EvidenceStatus, tuple[str, ...]]:
        if evidence_type is EvidenceType.BLOCKED_CAPABILITY_EVIDENCE:
            return EvidenceStatus.BLOCKED, ("BLOCKED_CAPABILITY",)
        if observation.run_id != context.research_agent_run_id:
            return EvidenceStatus.INVALID, ("OBSERVATION_RUN_MISMATCH",)
        if observation.security_id != context.security_id:
            return EvidenceStatus.INVALID, ("OBSERVATION_SECURITY_MISMATCH",)
        if observation.snapshot_id != context.snapshot_id:
            return EvidenceStatus.INVALID, ("OBSERVATION_SNAPSHOT_MISMATCH",)
        if observation.research_as_of_time != context.research_as_of_time:
            return EvidenceStatus.INVALID, ("OBSERVATION_AS_OF_MISMATCH",)
        if real_research and synthetic_status in {
            SyntheticStatus.SYNTHETIC_TEST_ONLY,
            SyntheticStatus.UNKNOWN,
        }:
            return EvidenceStatus.INVALID, ("SYNTHETIC_EVIDENCE_FOR_REAL_RUN",)
        if not source.exists:
            return EvidenceStatus.SOURCE_MISSING, ("SOURCE_RECORD_MISSING",)
        if source.checksum != source.expected_checksum:
            return EvidenceStatus.INVALID, ("SOURCE_CHECKSUM_MISMATCH",)
        if source.security_id != context.security_id:
            return EvidenceStatus.INVALID, ("EVIDENCE_SECURITY_MISMATCH",)
        if source.snapshot_id != context.snapshot_id:
            return EvidenceStatus.INVALID, ("EVIDENCE_SNAPSHOT_MISMATCH",)
        if source.published_at is not None and source.published_at > context.research_as_of_time:
            return EvidenceStatus.FUTURE_DATA, ("FUTURE_DATA",)
        if evidence_type is EvidenceType.DOCUMENT_CITATION_EVIDENCE:
            if source.citation_id is None:
                return EvidenceStatus.INVALID, ("CITATION_MISSING",)
            if source.citation_valid is not True:
                return EvidenceStatus.INVALID, ("INVALID_CITATION",)
            if source.published_at is None:
                return EvidenceStatus.INVALID, ("PUBLISHED_AT_UNKNOWN",)
        if evidence_type in {
            EvidenceType.DERIVED_METRIC_EVIDENCE,
            EvidenceType.METRIC_LINEAGE_EVIDENCE,
        } and (
            source.calculation_run_id is None
            or not source.calculation_input_ids
            or source.formula_version is None
            or source.metric_lineage_valid is not True
        ):
            return EvidenceStatus.INVALID, ("INVALID_METRIC_LINEAGE",)
        return EvidenceStatus.VALID, ()
