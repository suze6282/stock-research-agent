from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.enums import (
    EvidenceStatus,
    EvidenceType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import ResearchEvidenceRecord

MODULE = "stock_research_agent.domain.research_agent.conflicts"
NOW = datetime(2026, 7, 24, 8, tzinfo=UTC)
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SECURITY_ID = UUID("22222222-2222-4222-8222-222222222222")
SNAPSHOT_ID = UUID("33333333-3333-4333-8333-333333333333")


def _module() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _evidence(index: int, **updates: object) -> ResearchEvidenceRecord:
    payload = {
        "metric_code": "REVENUE",
        "period": "FY2025",
        "value": "100",
        "unit": "MILLION",
        "currency_code": "USD",
        "provider": "provider-a",
        "restatement_version": "v1",
        "document_assertion": "POSITIVE",
    }
    payload.update(updates.pop("payload", {}))
    values = {
        "id": UUID(int=index),
        "run_id": RUN_ID,
        "observation_id": UUID(int=100 + index),
        "evidence_type": EvidenceType.STRUCTURED_FACT_EVIDENCE,
        "status": EvidenceStatus.VALID,
        "schema_version": "evidence-v1",
        "security_id": SECURITY_ID,
        "snapshot_id": SNAPSHOT_ID,
        "research_as_of_time": NOW,
        "source_record_type": "fact",
        "source_record_id": UUID(int=200 + index),
        "source_checksum": f"{index:064x}",
        "published_at": NOW,
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "payload": payload,
        "created_at": NOW,
    }
    values.update(updates)
    return ResearchEvidenceRecord.model_validate(values)


@pytest.mark.parametrize(
    ("left", "right", "reason"),
    (
        ({}, {"payload": {"value": "101"}}, "VALUE_CONFLICT"),
        ({}, {"payload": {"provider": "provider-b", "value": "101"}}, "PROVIDER_CONFLICT"),
        (
            {},
            {"payload": {"restatement_version": "v2", "value": "101"}},
            "RESTATEMENT_CONFLICT",
        ),
        (
            {},
            {"payload": {"document_assertion": "NEGATIVE"}},
            "DOCUMENT_ASSERTION_CONFLICT",
        ),
        ({}, {"payload": {"currency_code": "CNY"}}, "CURRENCY_CONFLICT"),
        ({}, {"payload": {"unit": "THOUSAND"}}, "UNIT_CONFLICT"),
        (
            {},
            {"security_id": UUID("99999999-9999-4999-8999-999999999999")},
            "SECURITY_CONFLICT",
        ),
        (
            {},
            {"snapshot_id": UUID("99999999-9999-4999-8999-999999999999")},
            "SNAPSHOT_CONFLICT",
        ),
        (
            {},
            {"status": EvidenceStatus.FUTURE_DATA},
            "FUTURE_DATA_CONFLICT",
        ),
        (
            {},
            {"synthetic_status": SyntheticStatus.SYNTHETIC_TEST_ONLY},
            "SYNTHETIC_REAL_CONFLICT",
        ),
    ),
)
def test_all_approved_conflicts_are_detected_without_resolution(
    left: dict[str, object],
    right: dict[str, object],
    reason: str,
) -> None:
    result = (
        _module().EvidenceConflictDetector().detect((_evidence(2, **right), _evidence(1, **left)))
    )

    assert result.conflicting is True
    assert reason in result.reason_codes
    assert result.evidence_ids == (UUID(int=1), UUID(int=2))


def test_identical_compatible_evidence_is_not_a_conflict() -> None:
    result = _module().EvidenceConflictDetector().detect((_evidence(2), _evidence(1)))

    assert result.conflicting is False
    assert result.reason_codes == ()
    assert result.evidence_ids == ()


def test_detector_is_order_invariant_and_never_mutates_or_chooses_a_winner() -> None:
    first = _evidence(1)
    second = _evidence(2, payload={"value": "999"})
    original = (first.model_dump(), second.model_dump())
    detector = _module().EvidenceConflictDetector()

    forward = detector.detect((first, second))
    reverse = detector.detect((second, first))

    assert forward == reverse
    assert forward.evidence_ids == (first.id, second.id)
    assert first.model_dump() == original[0]
    assert second.model_dump() == original[1]
    assert not hasattr(forward, "selected_evidence_id")
    assert not hasattr(forward, "resolved_value")
