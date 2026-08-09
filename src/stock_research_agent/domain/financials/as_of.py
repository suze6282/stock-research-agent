"""Deterministic point-in-time fact-version selection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from stock_research_agent.domain.financials.enums import QualityStatus


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone aware")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class FactVersionCandidate:
    fact_id: UUID
    identity_key: str
    value: Decimal
    source_published_at: datetime | None
    retrieved_at: datetime
    is_restated: bool

    def __post_init__(self) -> None:
        if not self.identity_key:
            raise ValueError("identity_key must not be empty")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("fact value must be a finite Decimal")
        object.__setattr__(
            self,
            "retrieved_at",
            _aware_utc(self.retrieved_at, field_name="retrieved_at"),
        )
        if self.source_published_at is not None:
            object.__setattr__(
                self,
                "source_published_at",
                _aware_utc(self.source_published_at, field_name="source_published_at"),
            )


@dataclass(frozen=True)
class AsOfFactSelection:
    status: QualityStatus
    selected_fact_ids: tuple[UUID, ...]
    excluded_fact_ids: tuple[UUID, ...]
    warnings: tuple[str, ...]


def _published_at(candidate: FactVersionCandidate) -> datetime:
    published_at = candidate.source_published_at
    if published_at is None:
        raise RuntimeError("eligible fact version is missing source_published_at")
    return published_at


def select_fact_versions_as_of(
    candidates: tuple[FactVersionCandidate, ...],
    research_as_of_time: datetime,
) -> AsOfFactSelection:
    """Select the latest unambiguous public version for each exact fact identity."""

    cutoff = _aware_utc(research_as_of_time, field_name="research_as_of_time")
    warnings: list[str] = []
    excluded: set[UUID] = set()
    eligible_by_identity: dict[str, list[FactVersionCandidate]] = defaultdict(list)

    for candidate in sorted(candidates, key=lambda item: (item.identity_key, str(item.fact_id))):
        if candidate.source_published_at is None:
            excluded.add(candidate.fact_id)
            warnings.append(f"SOURCE_PUBLISHED_AT_UNKNOWN:{candidate.fact_id}")
        elif candidate.source_published_at > cutoff:
            excluded.add(candidate.fact_id)
        else:
            eligible_by_identity[candidate.identity_key].append(candidate)

    selected: list[FactVersionCandidate] = []
    for identity_key in sorted(eligible_by_identity):
        versions = eligible_by_identity[identity_key]
        latest_publication = max(_published_at(version) for version in versions)
        latest = sorted(
            (version for version in versions if version.source_published_at == latest_publication),
            key=lambda item: str(item.fact_id),
        )
        if len(latest) > 1 and len({version.value for version in latest}) > 1:
            warnings.append(f"CONFLICTING_FACT_VERSIONS:{identity_key}")
            excluded.update(version.fact_id for version in versions)
            continue
        chosen = latest[0]
        selected.append(chosen)
        excluded.update(
            version.fact_id for version in versions if version.fact_id != chosen.fact_id
        )
        if len(latest) > 1:
            warnings.append(f"DUPLICATE_FACT_VERSION:{identity_key}")

    if not selected:
        if not warnings:
            warnings.append("NO_FACTS_AS_OF")
        status = QualityStatus.BLOCKED
    elif warnings:
        status = QualityStatus.PARTIAL
    else:
        status = QualityStatus.PASS
    return AsOfFactSelection(
        status=status,
        selected_fact_ids=tuple(candidate.fact_id for candidate in selected),
        excluded_fact_ids=tuple(sorted(excluded, key=str)),
        warnings=tuple(sorted(warnings)),
    )
