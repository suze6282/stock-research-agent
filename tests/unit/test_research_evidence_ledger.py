from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.enums import (
    EvidenceStatus,
    EvidenceType,
    ObservationStatus,
    ObservationType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ControlledRunContext,
    ResearchObservationRecord,
)

MODULE = "stock_research_agent.domain.research_agent.evidence"
NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SECURITY_ID = UUID("22222222-2222-4222-8222-222222222222")
SNAPSHOT_ID = UUID("33333333-3333-4333-8333-333333333333")
SOURCE_ID = UUID("44444444-4444-4444-8444-444444444444")
CHECKSUM = "a" * 64
STEP_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _module() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _context() -> ControlledRunContext:
    return ControlledRunContext(
        security_id=SECURITY_ID,
        snapshot_id=SNAPSHOT_ID,
        research_as_of_time=NOW,
        research_agent_run_id=RUN_ID,
        research_request_id=UUID("55555555-5555-4555-8555-555555555555"),
        policy_version="controlled-offline-v1",
        tool_catalog_version="tool-catalog-v1:" + "b" * 64,
    )


def _observation(**updates: object) -> ResearchObservationRecord:
    values = {
        "id": UUID("66666666-6666-4666-8666-666666666666"),
        "run_id": RUN_ID,
        "research_step_id": STEP_ID,
        "invocation_id": UUID("77777777-7777-4777-8777-777777777777"),
        "observation_type": ObservationType.STRUCTURED_METRIC,
        "status": ObservationStatus.PASS,
        "schema_version": "observation-v1",
        "payload": {"value": "12.50"},
        "output_checksum": "c" * 64,
        "security_id": SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": NOW,
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "warnings": (),
        "created_at": NOW,
    }
    values.update(updates)
    return ResearchObservationRecord.model_validate(values)


def _source(**updates: object) -> object:
    evidence = _module()
    values = {
        "record_type": "derived_metric",
        "record_id": SOURCE_ID,
        "checksum": CHECKSUM,
        "expected_checksum": CHECKSUM,
        "exists": True,
        "security_id": SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
        "published_at": NOW - timedelta(days=1),
        "citation_id": None,
        "citation_valid": None,
        "calculation_run_id": UUID("88888888-8888-4888-8888-888888888888"),
        "calculation_input_ids": (UUID("99999999-9999-4999-8999-999999999999"),),
        "formula_version": "formula-v1",
        "metric_lineage_valid": True,
        "payload": {"value": "12.50", "unit": "CNY"},
    }
    values.update(updates)
    return evidence.EvidenceSource(**values)


def _admit(
    *,
    evidence_type: EvidenceType = EvidenceType.DERIVED_METRIC_EVIDENCE,
    observation: ResearchObservationRecord | None = None,
    source: object | None = None,
    synthetic_status: SyntheticStatus = SyntheticStatus.REAL_VERIFIED,
    real_research: bool = True,
) -> object:
    evidence = _module()
    return evidence.EvidenceLedgerService().admit(
        evidence_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        context=_context(),
        observation=observation or _observation(),
        evidence_type=evidence_type,
        source=source or _source(),
        synthetic_status=synthetic_status,
        real_research=real_research,
        created_at=NOW,
    )


def test_valid_metric_evidence_requires_complete_calculation_lineage() -> None:
    result = _admit()

    assert result.status is EvidenceStatus.VALID
    assert result.run_id == RUN_ID
    assert result.security_id == SECURITY_ID
    assert result.snapshot_id == SNAPSHOT_ID
    assert result.source_record_id == SOURCE_ID
    assert result.source_checksum == CHECKSUM
    assert result.calculation_run_id is not None
    assert len(result.calculation_input_ids) == 1
    assert result.formula_version == "formula-v1"


@pytest.mark.parametrize(
    ("source_updates", "status", "warning"),
    (
        ({"exists": False}, EvidenceStatus.SOURCE_MISSING, "SOURCE_RECORD_MISSING"),
        ({"expected_checksum": "f" * 64}, EvidenceStatus.INVALID, "SOURCE_CHECKSUM_MISMATCH"),
        (
            {"security_id": UUID(int=0)},
            EvidenceStatus.INVALID,
            "EVIDENCE_SECURITY_MISMATCH",
        ),
        (
            {"snapshot_id": UUID(int=0)},
            EvidenceStatus.INVALID,
            "EVIDENCE_SNAPSHOT_MISMATCH",
        ),
        (
            {"published_at": NOW + timedelta(seconds=1)},
            EvidenceStatus.FUTURE_DATA,
            "FUTURE_DATA",
        ),
        (
            {"metric_lineage_valid": False},
            EvidenceStatus.INVALID,
            "INVALID_METRIC_LINEAGE",
        ),
        (
            {"calculation_input_ids": ()},
            EvidenceStatus.INVALID,
            "INVALID_METRIC_LINEAGE",
        ),
    ),
)
def test_invalid_metric_sources_remain_auditable(
    source_updates: dict[str, object],
    status: EvidenceStatus,
    warning: str,
) -> None:
    result = _admit(source=_source(**source_updates))

    assert result.status is status
    assert warning in result.warning_codes
    assert result.source_record_id == SOURCE_ID


@pytest.mark.parametrize(
    ("updates", "status", "warning"),
    (
        ({"citation_valid": False}, EvidenceStatus.INVALID, "INVALID_CITATION"),
        ({"published_at": None}, EvidenceStatus.INVALID, "PUBLISHED_AT_UNKNOWN"),
        ({"citation_id": None}, EvidenceStatus.INVALID, "CITATION_MISSING"),
    ),
)
def test_document_evidence_requires_valid_citation_and_known_publication(
    updates: dict[str, object],
    status: EvidenceStatus,
    warning: str,
) -> None:
    source_values = {
        "citation_id": UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        "citation_valid": True,
        "calculation_run_id": None,
        "calculation_input_ids": (),
        "formula_version": None,
        "metric_lineage_valid": None,
    }
    source_values.update(updates)
    source = _source(**source_values)

    result = _admit(
        evidence_type=EvidenceType.DOCUMENT_CITATION_EVIDENCE,
        source=source,
    )

    assert result.status is status
    assert warning in result.warning_codes


def test_synthetic_or_unknown_evidence_is_invalid_for_real_company_run() -> None:
    for synthetic in (
        SyntheticStatus.SYNTHETIC_TEST_ONLY,
        SyntheticStatus.UNKNOWN,
    ):
        result = _admit(synthetic_status=synthetic)
        assert result.status is EvidenceStatus.INVALID
        assert "SYNTHETIC_EVIDENCE_FOR_REAL_RUN" in result.warning_codes


def test_blocked_capability_is_recorded_but_cannot_become_valid_fact() -> None:
    result = _admit(
        evidence_type=EvidenceType.BLOCKED_CAPABILITY_EVIDENCE,
        observation=_observation(
            observation_type=ObservationType.BLOCKED_CAPABILITY,
            status=ObservationStatus.BLOCKED,
            payload={"capability_code": "DOCUMENT_BODY_UNAVAILABLE"},
        ),
        source=_source(exists=False),
    )

    assert result.status is EvidenceStatus.BLOCKED
    assert result.source_record_id == SOURCE_ID
    assert "BLOCKED_CAPABILITY" in result.warning_codes


def test_observation_lineage_mismatch_is_never_admitted_as_valid() -> None:
    result = _admit(observation=_observation(run_id=UUID(int=0)))

    assert result.status is EvidenceStatus.INVALID
    assert "OBSERVATION_RUN_MISMATCH" in result.warning_codes
