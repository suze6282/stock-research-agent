"""Deterministic research-as-of and append-only Provider revision rules."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from stock_research_agent.domain.providers.schemas import (
    AwareUtcDateTime,
    Checksum,
    FrozenProviderContract,
    SemanticVersion,
)


class ProviderTemporalStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    REUSED = "REUSED"


class ProviderTemporalRecord(FrozenProviderContract):
    provider_definition_id: UUID
    provider_capability_id: UUID
    source_identity: str = Field(min_length=1, max_length=512)
    revision: int = Field(ge=1, le=1_000_000)
    source_checksum: Checksum
    raw_artifact_id: UUID
    manifest_id: UUID
    source_published_at: AwareUtcDateTime | None
    retrieved_at: AwareUtcDateTime
    supersedes_revision: int | None = Field(default=None, ge=1, le=999_999)
    is_restatement: bool
    license_policy_version: SemanticVersion

    @property
    def source_key(self) -> tuple[UUID, UUID, str]:
        return (
            self.provider_definition_id,
            self.provider_capability_id,
            self.source_identity,
        )

    @property
    def revision_key(self) -> tuple[UUID, UUID, str, int]:
        return (*self.source_key, self.revision)


class ProviderTemporalDecision(FrozenProviderContract):
    status: ProviderTemporalStatus
    eligible: bool
    warning_codes: tuple[str, ...]
    record: ProviderTemporalRecord
    append_required: bool
    preserved_history: tuple[ProviderTemporalRecord, ...]


class ProviderTemporalValidator:
    """Validate as-of eligibility without selecting or erasing a revision."""

    def __init__(self, history: Iterable[ProviderTemporalRecord] = ()) -> None:
        ordered = tuple(
            sorted(
                history,
                key=lambda record: (
                    str(record.provider_definition_id),
                    str(record.provider_capability_id),
                    record.source_identity,
                    record.revision,
                ),
            )
        )
        keys = tuple(record.revision_key for record in ordered)
        if len(keys) != len(set(keys)):
            raise ValueError("PROVIDER_REVISION_HISTORY_DUPLICATE")
        self._history = ordered

    def validate(
        self,
        record: ProviderTemporalRecord,
        research_as_of: AwareUtcDateTime,
        *,
        strict_historical: bool = True,
    ) -> ProviderTemporalDecision:
        existing = next(
            (item for item in self._history if item.revision_key == record.revision_key),
            None,
        )
        if existing is not None:
            if existing != record:
                raise ValueError("PROVIDER_REVISION_OVERWRITE_FORBIDDEN")
            return ProviderTemporalDecision(
                status=ProviderTemporalStatus.REUSED,
                eligible=_is_temporally_eligible(record, research_as_of, strict_historical),
                warning_codes=_temporal_warnings(record, research_as_of),
                record=existing,
                append_required=False,
                preserved_history=self._history,
            )

        related = tuple(item for item in self._history if item.source_key == record.source_key)
        self._validate_append(record, related)
        status, eligible, warnings = _temporal_status(
            record,
            research_as_of,
            strict_historical,
        )
        return ProviderTemporalDecision(
            status=status,
            eligible=eligible,
            warning_codes=warnings,
            record=record,
            append_required=True,
            preserved_history=self._history,
        )

    def eligible_history(
        self,
        research_as_of: AwareUtcDateTime,
        *,
        strict_historical: bool = True,
    ) -> tuple[ProviderTemporalRecord, ...]:
        return tuple(
            record
            for record in self._history
            if _is_temporally_eligible(record, research_as_of, strict_historical)
        )

    @staticmethod
    def _validate_append(
        record: ProviderTemporalRecord,
        related: tuple[ProviderTemporalRecord, ...],
    ) -> None:
        if not related:
            if record.revision != 1 or record.supersedes_revision is not None:
                raise ValueError("PROVIDER_REVISION_APPEND_INVALID")
            return
        previous = max(related, key=lambda item: item.revision)
        if (
            record.revision != previous.revision + 1
            or record.supersedes_revision != previous.revision
            or record.source_checksum == previous.source_checksum
            or record.raw_artifact_id == previous.raw_artifact_id
            or record.manifest_id == previous.manifest_id
        ):
            raise ValueError("PROVIDER_REVISION_APPEND_INVALID")


def _temporal_status(
    record: ProviderTemporalRecord,
    research_as_of: AwareUtcDateTime,
    strict_historical: bool,
) -> tuple[ProviderTemporalStatus, bool, tuple[str, ...]]:
    warnings = _temporal_warnings(record, research_as_of)
    if warnings in {
        ("SOURCE_PUBLISHED_AFTER_AS_OF",),
        ("RETRIEVED_AFTER_AS_OF",),
    }:
        return ProviderTemporalStatus.BLOCKED, False, warnings
    if warnings == ("UNKNOWN_PUBLISHED_AT",):
        if strict_historical:
            return ProviderTemporalStatus.BLOCKED, False, warnings
        return ProviderTemporalStatus.PARTIAL, True, warnings
    return ProviderTemporalStatus.ELIGIBLE, True, ()


def _temporal_warnings(
    record: ProviderTemporalRecord,
    research_as_of: AwareUtcDateTime,
) -> tuple[str, ...]:
    if record.source_published_at is None:
        return ("UNKNOWN_PUBLISHED_AT",)
    if record.source_published_at > research_as_of:
        return ("SOURCE_PUBLISHED_AFTER_AS_OF",)
    if record.retrieved_at > research_as_of:
        return ("RETRIEVED_AFTER_AS_OF",)
    return ()


def _is_temporally_eligible(
    record: ProviderTemporalRecord,
    research_as_of: AwareUtcDateTime,
    strict_historical: bool,
) -> bool:
    return _temporal_status(record, research_as_of, strict_historical)[1]


__all__ = [
    "ProviderTemporalDecision",
    "ProviderTemporalRecord",
    "ProviderTemporalStatus",
    "ProviderTemporalValidator",
]
