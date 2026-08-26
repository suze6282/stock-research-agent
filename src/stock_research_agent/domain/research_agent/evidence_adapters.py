"""Fail-closed production mapping from persisted Observations to Evidence admission."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue

from stock_research_agent.domain.data_access.schemas import DataSnapshotRecord
from stock_research_agent.domain.research_agent.canonical import stable_checksum
from stock_research_agent.domain.research_agent.enums import (
    EvidenceType,
    ObservationStatus,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.evidence import (
    EvidenceLedgerService,
    EvidenceSource,
)
from stock_research_agent.domain.research_agent.schemas import (
    ControlledRunContext,
    ResearchEvidenceWrite,
    ResearchObservationRecord,
)
from stock_research_agent.domain.securities.schemas import SecurityDetail

SECURITY_MASTER_IDENTITY_SOURCE_RECORD_TYPE = "SECURITY_MASTER_IDENTITY_V1"


class SnapshotEvidenceSourceRepository(Protocol):
    def get_snapshot(self, snapshot_id: UUID) -> DataSnapshotRecord | None: ...


class SecurityIdentitySourceRepository(Protocol):
    def get_security(self, security_id: UUID) -> SecurityDetail | None: ...


_FACTUAL_EVIDENCE_TYPES: dict[str, EvidenceType] = {
    "get_normalized_financial_facts": EvidenceType.STRUCTURED_FACT_EVIDENCE,
    "get_financial_metrics": EvidenceType.DERIVED_METRIC_EVIDENCE,
    "get_metric_lineage": EvidenceType.METRIC_LINEAGE_EVIDENCE,
    "get_corporate_actions": EvidenceType.CORPORATE_ACTION_EVIDENCE,
    "search_document_chunks": EvidenceType.DOCUMENT_CITATION_EVIDENCE,
}


class ProductionObservationEvidenceAdapter:
    """Create one auditable Evidence candidate without trusting Tool success."""

    def __init__(
        self,
        *,
        snapshots: SnapshotEvidenceSourceRepository,
        ledger: EvidenceLedgerService,
        id_factory: Callable[[], UUID],
        clock: Callable[[], datetime],
    ) -> None:
        self._snapshots = snapshots
        self._ledger = ledger
        self._id_factory = id_factory
        self._clock = clock

    def admit(
        self,
        *,
        context: ControlledRunContext,
        tool_name: str,
        observation: ResearchObservationRecord,
        real_research: bool,
    ) -> ResearchEvidenceWrite:
        evidence_type, source, synthetic_status = self._candidate(
            tool_name=tool_name,
            observation=observation,
        )
        return self._ledger.admit(
            evidence_id=self._id_factory(),
            context=context,
            observation=observation,
            evidence_type=evidence_type,
            source=source,
            synthetic_status=synthetic_status,
            real_research=real_research,
            created_at=self._clock(),
        )

    def admit_security_identity(
        self,
        *,
        context: ControlledRunContext,
        observation: ResearchObservationRecord,
        security_master: SecurityIdentitySourceRepository,
        real_research: bool,
    ) -> ResearchEvidenceWrite:
        detail = security_master.get_security(context.security_id)
        source = _security_identity_source(
            context=context,
            observation=observation,
            detail=detail,
        )
        return self._ledger.admit(
            evidence_id=self._id_factory(),
            context=context,
            observation=observation,
            evidence_type=EvidenceType.SECURITY_MASTER_EVIDENCE,
            source=source,
            synthetic_status=observation.synthetic_status,
            real_research=real_research,
            created_at=self._clock(),
        )

    def _candidate(
        self,
        *,
        tool_name: str,
        observation: ResearchObservationRecord,
    ) -> tuple[EvidenceType, EvidenceSource, SyntheticStatus]:
        if observation.status is ObservationStatus.BLOCKED:
            return (
                EvidenceType.BLOCKED_CAPABILITY_EVIDENCE,
                _observation_source(
                    observation,
                    payload={
                        "capability_code": _capability_code(tool_name, observation),
                        "tool_name": tool_name,
                    },
                ),
                observation.synthetic_status,
            )
        if tool_name == "get_data_snapshot":
            return (
                EvidenceType.SNAPSHOT_EVIDENCE,
                self._snapshot_source(observation),
                observation.synthetic_status,
            )
        if observation.status is ObservationStatus.PARTIAL:
            return (
                EvidenceType.DATA_QUALITY_EVIDENCE,
                _observation_source(
                    observation,
                    payload={
                        "quality_code": _quality_code(tool_name, observation),
                        "tool_name": tool_name,
                    },
                ),
                observation.synthetic_status,
            )
        evidence_type = _FACTUAL_EVIDENCE_TYPES.get(
            tool_name,
            EvidenceType.DATA_QUALITY_EVIDENCE,
        )
        return (
            evidence_type,
            _missing_source(tool_name, observation),
            observation.synthetic_status,
        )

    def _snapshot_source(self, observation: ResearchObservationRecord) -> EvidenceSource:
        snapshot = self._snapshots.get_snapshot(observation.snapshot_id)
        expected_checksum = _snapshot_checksum(observation.payload)
        if snapshot is None or snapshot.checksum is None or expected_checksum is None:
            return _missing_source("get_data_snapshot", observation)
        return EvidenceSource(
            record_type="data_snapshots",
            record_id=snapshot.id,
            checksum=snapshot.checksum,
            expected_checksum=expected_checksum,
            exists=True,
            security_id=snapshot.security_id,
            snapshot_id=snapshot.id,
            published_at=None,
            citation_id=None,
            citation_valid=None,
            calculation_run_id=None,
            calculation_input_ids=(),
            formula_version=None,
            metric_lineage_valid=None,
            payload={
                "snapshot_id": str(snapshot.id),
                "snapshot_status": snapshot.status,
                "quality_code": "SNAPSHOT_PARTIAL"
                if snapshot.status == "PARTIAL"
                else "SNAPSHOT_COMPLETE",
            },
        )


def _observation_source(
    observation: ResearchObservationRecord,
    *,
    payload: dict[str, JsonValue],
) -> EvidenceSource:
    return EvidenceSource(
        record_type="research_observations",
        record_id=observation.id,
        checksum=observation.output_checksum,
        expected_checksum=stable_checksum(observation.payload),
        exists=True,
        security_id=observation.security_id,
        snapshot_id=observation.snapshot_id,
        published_at=None,
        citation_id=None,
        citation_valid=None,
        calculation_run_id=None,
        calculation_input_ids=(),
        formula_version=None,
        metric_lineage_valid=None,
        payload=payload,
    )


def _missing_source(tool_name: str, observation: ResearchObservationRecord) -> EvidenceSource:
    source_ids = observation.payload.get("source_record_ids")
    source_id = observation.id
    if isinstance(source_ids, list) and source_ids:
        try:
            source_id = UUID(str(source_ids[0]))
        except ValueError:
            source_id = observation.id
    return EvidenceSource(
        record_type=f"{tool_name}_source",
        record_id=source_id,
        checksum=observation.output_checksum,
        expected_checksum=stable_checksum(observation.payload),
        exists=False,
        security_id=observation.security_id,
        snapshot_id=observation.snapshot_id,
        published_at=None,
        citation_id=None,
        citation_valid=None,
        calculation_run_id=None,
        calculation_input_ids=(),
        formula_version=None,
        metric_lineage_valid=None,
        payload={"tool_name": tool_name},
    )


def _snapshot_checksum(payload: Mapping[str, JsonValue]) -> str | None:
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        return None
    checksum = data[0].get("checksum")
    return checksum if isinstance(checksum, str) else None


def security_master_identity_projection(detail: SecurityDetail) -> dict[str, JsonValue]:
    """Freeze the approved V1 Security Master identity projection."""
    return {
        "security_id": str(detail.security.id),
        "issuer_id": str(detail.issuer.id),
        "issuer": detail.issuer.legal_name,
        "symbol": detail.security.symbol,
        "exchange_mic": detail.exchange.mic,
        "exchange": detail.exchange.mic,
    }


def security_master_identity_checksum(projection: Mapping[str, JsonValue]) -> str:
    return stable_checksum(
        {
            "source_record_type": SECURITY_MASTER_IDENTITY_SOURCE_RECORD_TYPE,
            "projection": projection,
        }
    )


def _security_identity_source(
    *,
    context: ControlledRunContext,
    observation: ResearchObservationRecord,
    detail: SecurityDetail | None,
) -> EvidenceSource:
    if detail is None:
        return EvidenceSource(
            record_type=SECURITY_MASTER_IDENTITY_SOURCE_RECORD_TYPE,
            record_id=context.security_id,
            checksum=security_master_identity_checksum(observation.payload),
            expected_checksum=security_master_identity_checksum(observation.payload),
            exists=False,
            security_id=context.security_id,
            snapshot_id=context.snapshot_id,
            published_at=None,
            citation_id=None,
            citation_valid=None,
            calculation_run_id=None,
            calculation_input_ids=(),
            formula_version=None,
            metric_lineage_valid=None,
            payload={},
        )
    projection = security_master_identity_projection(detail)
    expected_checksum = security_master_identity_checksum(observation.payload)
    if observation.output_checksum != stable_checksum(observation.payload):
        expected_checksum = stable_checksum(
            {
                "invalid_observation_checksum": observation.output_checksum,
                "projection": observation.payload,
            }
        )
    return EvidenceSource(
        record_type=SECURITY_MASTER_IDENTITY_SOURCE_RECORD_TYPE,
        record_id=detail.security.id,
        checksum=security_master_identity_checksum(projection),
        expected_checksum=expected_checksum,
        exists=True,
        security_id=detail.security.id,
        snapshot_id=context.snapshot_id,
        published_at=None,
        citation_id=None,
        citation_valid=None,
        calculation_run_id=None,
        calculation_input_ids=(),
        formula_version=None,
        metric_lineage_valid=None,
        payload=projection,
    )


def _capability_code(tool_name: str, observation: ResearchObservationRecord) -> str:
    return _first_warning(observation) or f"{tool_name.upper()}_BLOCKED"


def _quality_code(tool_name: str, observation: ResearchObservationRecord) -> str:
    return _first_warning(observation) or f"{tool_name.upper()}_PARTIAL"


def _first_warning(observation: ResearchObservationRecord) -> str | None:
    return observation.warnings[0] if observation.warnings else None


__all__ = [
    "ProductionObservationEvidenceAdapter",
    "SECURITY_MASTER_IDENTITY_SOURCE_RECORD_TYPE",
    "SecurityIdentitySourceRepository",
    "SnapshotEvidenceSourceRepository",
    "security_master_identity_checksum",
    "security_master_identity_projection",
]
