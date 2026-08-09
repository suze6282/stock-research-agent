"""Deterministic, non-resolving Evidence conflict detection."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations

from stock_research_agent.domain.research_agent.enums import (
    EvidenceStatus,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ConflictResult,
    ResearchEvidenceRecord,
)

_REASON_ORDER = (
    "SECURITY_CONFLICT",
    "SNAPSHOT_CONFLICT",
    "FUTURE_DATA_CONFLICT",
    "SYNTHETIC_REAL_CONFLICT",
    "CURRENCY_CONFLICT",
    "UNIT_CONFLICT",
    "VALUE_CONFLICT",
    "PROVIDER_CONFLICT",
    "RESTATEMENT_CONFLICT",
    "DOCUMENT_ASSERTION_CONFLICT",
)


class EvidenceConflictDetector:
    """Compare the complete set and preserve every record on conflict."""

    def detect(
        self,
        evidence: Sequence[ResearchEvidenceRecord],
    ) -> ConflictResult:
        reasons: set[str] = set()
        if len({item.security_id for item in evidence}) > 1:
            reasons.add("SECURITY_CONFLICT")
        if len({item.snapshot_id for item in evidence}) > 1:
            reasons.add("SNAPSHOT_CONFLICT")
        if any(item.status is EvidenceStatus.FUTURE_DATA for item in evidence):
            reasons.add("FUTURE_DATA_CONFLICT")

        synthetic = {item.synthetic_status for item in evidence}
        real = {
            SyntheticStatus.REAL_VERIFIED,
            SyntheticStatus.FIXTURE_REAL_EXCERPT,
        }
        if synthetic.intersection(real) and SyntheticStatus.SYNTHETIC_TEST_ONLY in synthetic:
            reasons.add("SYNTHETIC_REAL_CONFLICT")

        for left, right in combinations(evidence, 2):
            if not _same_subject(left, right):
                continue
            _compare_payload(left, right, reasons)

        ordered = tuple(reason for reason in _REASON_ORDER if reason in reasons)
        ids = tuple(sorted((item.id for item in evidence), key=str)) if ordered else ()
        return ConflictResult(
            conflicting=bool(ordered),
            reason_codes=ordered,
            evidence_ids=ids,
        )


def _same_subject(
    left: ResearchEvidenceRecord,
    right: ResearchEvidenceRecord,
) -> bool:
    return left.payload.get("metric_code") == right.payload.get("metric_code") and left.payload.get(
        "period"
    ) == right.payload.get("period")


def _compare_payload(
    left: ResearchEvidenceRecord,
    right: ResearchEvidenceRecord,
    reasons: set[str],
) -> None:
    comparisons = (
        ("currency_code", "CURRENCY_CONFLICT"),
        ("unit", "UNIT_CONFLICT"),
        ("value", "VALUE_CONFLICT"),
        ("provider", "PROVIDER_CONFLICT"),
        ("restatement_version", "RESTATEMENT_CONFLICT"),
        ("document_assertion", "DOCUMENT_ASSERTION_CONFLICT"),
    )
    for field, reason in comparisons:
        left_value = left.payload.get(field)
        right_value = right.payload.get(field)
        if left_value is not None and right_value is not None and left_value != right_value:
            reasons.add(reason)
