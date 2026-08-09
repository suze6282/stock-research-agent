from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from stock_research_agent.domain.financials.as_of import (
    FactVersionCandidate,
    select_fact_versions_as_of,
)
from stock_research_agent.domain.financials.enums import QualityStatus

FACT_1 = UUID("10000000-0000-0000-0000-000000000001")
FACT_2 = UUID("10000000-0000-0000-0000-000000000002")
FACT_3 = UUID("10000000-0000-0000-0000-000000000003")


def _candidate(
    fact_id: UUID,
    *,
    identity_key: str = "REVENUE:FY2025",
    value: str = "100",
    published: datetime | None = datetime(2026, 2, 1, tzinfo=UTC),
    retrieved: datetime = datetime(2026, 7, 1, tzinfo=UTC),
    restated: bool = False,
) -> FactVersionCandidate:
    return FactVersionCandidate(
        fact_id=fact_id,
        identity_key=identity_key,
        value=Decimal(value),
        source_published_at=published,
        retrieved_at=retrieved,
        is_restated=restated,
    )


def test_future_version_is_invisible_to_earlier_cutoff() -> None:
    original = _candidate(FACT_1, published=datetime(2026, 2, 1, tzinfo=UTC))
    correction = _candidate(
        FACT_2,
        value="90",
        published=datetime(2026, 5, 1, tzinfo=UTC),
        restated=True,
    )

    early = select_fact_versions_as_of(
        (correction, original),
        datetime(2026, 3, 1, tzinfo=UTC),
    )
    later = select_fact_versions_as_of(
        (correction, original),
        datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert early.selected_fact_ids == (FACT_1,)
    assert correction.fact_id in early.excluded_fact_ids
    assert early.status is QualityStatus.PASS
    assert later.selected_fact_ids == (FACT_2,)
    assert later.status is QualityStatus.PASS


def test_unknown_publication_is_not_replaced_by_retrieval_time() -> None:
    unknown = _candidate(
        FACT_1,
        published=None,
        retrieved=datetime(2025, 1, 1, tzinfo=UTC),
    )

    result = select_fact_versions_as_of((unknown,), datetime(2026, 3, 1, tzinfo=UTC))

    assert result.status is QualityStatus.BLOCKED
    assert result.selected_fact_ids == ()
    assert result.excluded_fact_ids == (FACT_1,)
    assert result.warnings == ("SOURCE_PUBLISHED_AT_UNKNOWN:10000000-0000-0000-0000-000000000001",)


def test_same_timestamp_conflicting_versions_are_not_silently_resolved() -> None:
    first = _candidate(FACT_1, value="100")
    conflict = _candidate(FACT_2, value="101")

    result = select_fact_versions_as_of(
        (conflict, first),
        datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert result.status is QualityStatus.BLOCKED
    assert result.selected_fact_ids == ()
    assert result.warnings == ("CONFLICTING_FACT_VERSIONS:REVENUE:FY2025",)


def test_identical_duplicate_is_deduplicated_stably_with_warning() -> None:
    larger_id = _candidate(FACT_2)
    smaller_id = _candidate(FACT_1)

    result = select_fact_versions_as_of(
        (larger_id, smaller_id),
        datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert result.status is QualityStatus.PARTIAL
    assert result.selected_fact_ids == (FACT_1,)
    assert result.warnings == ("DUPLICATE_FACT_VERSION:REVENUE:FY2025",)


def test_candidate_order_does_not_change_selection_or_warnings() -> None:
    facts = (
        _candidate(FACT_1, identity_key="REVENUE:FY2025"),
        _candidate(FACT_2, identity_key="NET_INCOME:FY2025", value="10"),
        _candidate(
            FACT_3,
            identity_key="REVENUE:FY2025",
            value="110",
            published=datetime(2026, 2, 2, tzinfo=UTC),
        ),
    )
    cutoff = datetime(2026, 3, 1, tzinfo=UTC)

    assert select_fact_versions_as_of(facts, cutoff) == select_fact_versions_as_of(
        tuple(reversed(facts)), cutoff
    )
    assert select_fact_versions_as_of(facts, cutoff).selected_fact_ids == (FACT_2, FACT_3)


def test_naive_cutoff_is_invalid() -> None:
    with pytest.raises(ValueError, match="timezone aware"):
        select_fact_versions_as_of((_candidate(FACT_1),), datetime(2026, 3, 1))
