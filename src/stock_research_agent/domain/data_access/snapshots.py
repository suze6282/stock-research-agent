"""Immutable point-in-time snapshot construction contracts and service."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from stock_research_agent.domain.common.clock import Clock, SystemClock
from stock_research_agent.domain.data_access.enums import DataCategory
from stock_research_agent.domain.data_access.repositories import (
    DataAccessRepository,
    StoredDataValidationError,
)
from stock_research_agent.domain.data_access.schemas import (
    CorporateActionRecord,
    DailyPriceBarRecord,
    DataSnapshotRecord,
    DataSnapshotUpdate,
    DataSnapshotWrite,
    ProviderFinancialFactRecord,
    SnapshotItemRecord,
    SnapshotItemWrite,
    SnapshotSourceRecordType,
    SourceDocumentRecord,
)

SnapshotSourceRecord = (
    DailyPriceBarRecord | CorporateActionRecord | ProviderFinancialFactRecord | SourceDocumentRecord
)

_SOURCE_TYPES: dict[DataCategory, str] = {
    DataCategory.DAILY_PRICES: "daily_price_bars",
    DataCategory.CORPORATE_ACTIONS: "corporate_actions",
    DataCategory.FINANCIAL_FACTS: "provider_financial_facts",
    DataCategory.FILING_METADATA: "source_documents",
}


class SnapshotErrorCode(StrEnum):
    VERSION_CONFLICT = "VERSION_CONFLICT"
    BUILD_FAILED = "BUILD_FAILED"
    PERSISTENCE_FAILED = "PERSISTENCE_FAILED"


_ERROR_MESSAGES: dict[SnapshotErrorCode, str] = {
    SnapshotErrorCode.VERSION_CONFLICT: "Snapshot version conflicts with existing evidence",
    SnapshotErrorCode.BUILD_FAILED: "Snapshot build failed safely",
    SnapshotErrorCode.PERSISTENCE_FAILED: "Snapshot persistence failed safely",
}


class SnapshotBuildError(RuntimeError):
    """Stable, non-sensitive failure raised by the internal snapshot service."""

    def __init__(self, code: SnapshotErrorCode) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])

    def __repr__(self) -> str:
        return f"SnapshotBuildError(code={self.code.value!r})"


class _SnapshotContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class SnapshotBuildRequest(_SnapshotContract):
    security_id: UUID
    research_as_of_time: datetime
    snapshot_version: int = Field(gt=0)
    categories: tuple[DataCategory, ...] = Field(min_length=1)
    exchange_timezone: str = Field(min_length=1, max_length=64)
    provider_preference: tuple[UUID, ...] = ()
    item_limit: int = Field(default=99, gt=0, le=99)

    @field_validator("research_as_of_time")
    @classmethod
    def normalize_research_as_of(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("research_as_of_time must be timezone aware")
        return value.astimezone(UTC)

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: tuple[DataCategory, ...]) -> tuple[DataCategory, ...]:
        supported = {
            DataCategory.DAILY_PRICES,
            DataCategory.CORPORATE_ACTIONS,
            DataCategory.FINANCIAL_FACTS,
            DataCategory.FILING_METADATA,
        }
        if len(set(value)) != len(value):
            raise ValueError("categories must not contain duplicates")
        if not set(value) <= supported:
            raise ValueError("categories contain an unsupported snapshot category")
        return tuple(sorted(value, key=lambda category: category.value))

    @field_validator("exchange_timezone")
    @classmethod
    def validate_exchange_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("exchange_timezone must be a valid IANA name") from error
        return value

    @field_validator("provider_preference")
    @classmethod
    def validate_provider_preference(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("provider_preference must not contain duplicates")
        return value


class SnapshotItemSummary(_SnapshotContract):
    item_id: UUID
    provider_id: UUID
    category: DataCategory
    source_record_type: SnapshotSourceRecordType
    source_record_id: UUID
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class SnapshotBuildResult(_SnapshotContract):
    snapshot: DataSnapshotRecord
    items: tuple[SnapshotItemSummary, ...]
    status: Literal["COMPLETE", "PARTIAL"]
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    warnings: tuple[str, ...] = ()


class SnapshotBuilder:
    def __init__(self, repository: DataAccessRepository, *, clock: Clock | None = None) -> None:
        self._repository = repository
        self._clock = clock or SystemClock()

    def build(self, request: SnapshotBuildRequest) -> SnapshotBuildResult:
        """Build or replay one immutable snapshot without owning the caller transaction."""

        initial = DataSnapshotWrite(
            security_id=request.security_id,
            research_as_of_time=request.research_as_of_time,
            snapshot_version=request.snapshot_version,
            status="BUILDING",
            formula_version="raw-data-v1",
        )
        try:
            snapshot, created = self._repository.get_or_create_snapshot(initial)
        except Exception:
            raise SnapshotBuildError(SnapshotErrorCode.PERSISTENCE_FAILED) from None

        terminal_replay = not created and snapshot.status != "BUILDING"
        try:
            selected, warnings = self._select(request)
            item_writes = tuple(self._item_write(record, category) for category, record in selected)
            checksum = self._snapshot_checksum(request, item_writes, warnings)
            status: Literal["COMPLETE", "PARTIAL"] = "PARTIAL" if warnings else "COMPLETE"
            if terminal_replay:
                if snapshot.status != status or snapshot.checksum != checksum:
                    raise SnapshotBuildError(SnapshotErrorCode.VERSION_CONFLICT)
                return self._replay(
                    snapshot,
                    status,
                    checksum,
                    warnings,
                    item_writes,
                )
            with self._repository.snapshot_attempt():
                persisted_items = tuple(
                    self._repository.add_snapshot_item(
                        item.model_copy(update={"snapshot_id": snapshot.id})
                    )
                    for item in item_writes
                )
                completed = self._repository.update_snapshot(
                    snapshot.id,
                    DataSnapshotUpdate(
                        status=status,
                        completed_at=self._now_utc(),
                        checksum=checksum,
                        notes=self._notes(warnings),
                    ),
                )
                result = SnapshotBuildResult(
                    snapshot=completed,
                    items=tuple(self._summary(item) for item in persisted_items),
                    status=status,
                    checksum=checksum,
                    warnings=warnings,
                )
            return result
        except SnapshotBuildError:
            if terminal_replay:
                raise
            self._mark_failed(snapshot.id)
            raise SnapshotBuildError(SnapshotErrorCode.BUILD_FAILED) from None
        except Exception:
            if terminal_replay:
                raise SnapshotBuildError(SnapshotErrorCode.BUILD_FAILED) from None
            self._mark_failed(snapshot.id)
            raise SnapshotBuildError(SnapshotErrorCode.BUILD_FAILED) from None

    def _select(
        self, request: SnapshotBuildRequest
    ) -> tuple[tuple[tuple[DataCategory, SnapshotSourceRecord], ...], tuple[str, ...]]:
        selected: list[tuple[DataCategory, SnapshotSourceRecord]] = []
        warnings: list[str] = []
        local_date = request.research_as_of_time.astimezone(
            ZoneInfo(request.exchange_timezone)
        ).date()
        for category in request.categories:
            candidates, preferred_missing = self._category_candidates(request, category, local_date)
            if preferred_missing:
                warnings.append(f"NO_PREFERRED_PROVIDER:{category.value}")
            eligible = [
                record
                for record in candidates
                if self._eligible(record, category, request.research_as_of_time, local_date)
            ]
            if len(eligible) > request.item_limit:
                warnings.append(f"TRUNCATED_CATEGORY:{category.value}")
            eligible = eligible[: request.item_limit]
            if not eligible:
                warnings.append(f"MISSING_CATEGORY:{category.value}")
                continue
            for record in eligible:
                selected.append((category, record))
                if self._published_at(record) is None:
                    warnings.append(
                        "UNKNOWN_PUBLICATION:"
                        f"{category.value}:{_SOURCE_TYPES[category]}:{record.id}"
                    )
        selected.sort(
            key=lambda value: (
                value[0].value,
                _SOURCE_TYPES[value[0]],
                str(value[1].id),
                str(value[1].provider_id),
            )
        )
        return tuple(selected), tuple(warnings)

    def _category_candidates(
        self,
        request: SnapshotBuildRequest,
        category: DataCategory,
        local_date: date,
    ) -> tuple[tuple[SnapshotSourceRecord, ...], bool]:
        if request.provider_preference:
            for provider_id in request.provider_preference:
                candidates = self._query_category(request, category, local_date, provider_id)
                eligible = tuple(
                    record
                    for record in candidates
                    if self._eligible(record, category, request.research_as_of_time, local_date)
                )
                if eligible:
                    return eligible, False
            return (), True
        return self._query_category(request, category, local_date, None), False

    def _query_category(
        self,
        request: SnapshotBuildRequest,
        category: DataCategory,
        local_date: date,
        provider_id: UUID | None,
    ) -> tuple[SnapshotSourceRecord, ...]:
        limit = request.item_limit + 1
        if category is DataCategory.DAILY_PRICES:
            return tuple(
                self._repository.list_daily_history(
                    request.security_id,
                    request.research_as_of_time,
                    local_date,
                    limit,
                    provider_id,
                )
            )
        if category is DataCategory.CORPORATE_ACTIONS:
            return tuple(
                self._repository.list_corporate_actions(
                    request.security_id,
                    request.research_as_of_time,
                    limit,
                    provider_id,
                )
            )
        if category is DataCategory.FINANCIAL_FACTS:
            return tuple(
                self._repository.list_financial_facts(
                    request.security_id,
                    request.research_as_of_time,
                    limit,
                    provider_id,
                )
            )
        return tuple(
            self._repository.list_source_documents(
                request.security_id,
                request.research_as_of_time,
                limit,
                provider_id,
            )
        )

    @staticmethod
    def _eligible(
        record: SnapshotSourceRecord,
        category: DataCategory,
        cutoff: datetime,
        local_date: date,
    ) -> bool:
        if record.retrieved_at > cutoff:
            return False
        published_at = SnapshotBuilder._published_at(record)
        if published_at is not None and published_at > cutoff:
            return False
        return not (
            category is DataCategory.DAILY_PRICES
            and cast(DailyPriceBarRecord, record).trading_date > local_date
        )

    @staticmethod
    def _published_at(record: SnapshotSourceRecord) -> datetime | None:
        if isinstance(record, SourceDocumentRecord):
            return record.published_at
        return record.source_published_at

    @staticmethod
    def _item_write(record: SnapshotSourceRecord, category: DataCategory) -> SnapshotItemWrite:
        published_at = SnapshotBuilder._published_at(record)
        descriptor = {
            "category": category.value,
            "provider_id": str(record.provider_id),
            "retrieved_at": SnapshotBuilder._utc_text(record.retrieved_at),
            "schema": "snapshot-item-v1",
            "source_published_at": (
                None if published_at is None else SnapshotBuilder._utc_text(published_at)
            ),
            "source_record_id": str(record.id),
            "source_record_type": _SOURCE_TYPES[category],
        }
        checksum_input = SnapshotBuilder._canonical(descriptor)
        return SnapshotItemWrite(
            snapshot_id=UUID(int=0),
            provider_id=record.provider_id,
            category=category,
            source_record_type=cast(
                Literal[
                    "daily_price_bars",
                    "corporate_actions",
                    "provider_financial_facts",
                    "source_documents",
                ],
                _SOURCE_TYPES[category],
            ),
            source_record_id=record.id,
            source_published_at=published_at,
            retrieved_at=record.retrieved_at,
            checksum_input=checksum_input,
            checksum=hashlib.sha256(checksum_input.encode("utf-8")).hexdigest(),
        )

    @staticmethod
    def _snapshot_checksum(
        request: SnapshotBuildRequest,
        items: Sequence[SnapshotItemWrite],
        warnings: tuple[str, ...],
    ) -> str:
        document = {
            "items": [
                {
                    "checksum": item.checksum,
                    "descriptor": json.loads(item.checksum_input),
                }
                for item in items
            ],
            "provider_preference": [str(value) for value in request.provider_preference],
            "research_as_of_time": SnapshotBuilder._utc_text(request.research_as_of_time),
            "requested_categories": [value.value for value in request.categories],
            "schema": "data-snapshot-v1",
            "security_id": str(request.security_id),
            "snapshot_version": request.snapshot_version,
            "warnings": list(warnings),
        }
        canonical = SnapshotBuilder._canonical(document)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _replay(
        self,
        snapshot: DataSnapshotRecord,
        status: Literal["COMPLETE", "PARTIAL"],
        checksum: str,
        warnings: tuple[str, ...],
        expected_items: Sequence[SnapshotItemWrite],
    ) -> SnapshotBuildResult:
        try:
            items = self._repository.list_snapshot_items_for_replay(snapshot.id)
        except StoredDataValidationError:
            raise SnapshotBuildError(SnapshotErrorCode.VERSION_CONFLICT) from None
        except Exception:
            raise SnapshotBuildError(SnapshotErrorCode.PERSISTENCE_FAILED) from None
        if not self._replay_items_match(items, expected_items):
            raise SnapshotBuildError(SnapshotErrorCode.VERSION_CONFLICT)
        return SnapshotBuildResult(
            snapshot=snapshot,
            items=tuple(self._summary(item) for item in items),
            status=status,
            checksum=checksum,
            warnings=warnings,
        )

    @staticmethod
    def _replay_items_match(
        stored_items: Sequence[SnapshotItemRecord],
        expected_items: Sequence[SnapshotItemWrite],
    ) -> bool:
        if len(stored_items) != len(expected_items):
            return False
        return all(
            (
                stored.provider_id,
                stored.category,
                stored.source_record_type,
                stored.source_record_id,
                stored.source_published_at,
                stored.retrieved_at,
                stored.checksum_input,
                stored.checksum,
            )
            == (
                expected.provider_id,
                expected.category,
                expected.source_record_type,
                expected.source_record_id,
                expected.source_published_at,
                expected.retrieved_at,
                expected.checksum_input,
                expected.checksum,
            )
            for stored, expected in zip(stored_items, expected_items, strict=True)
        )

    def _mark_failed(self, snapshot_id: UUID) -> None:
        try:
            self._repository.update_snapshot(
                snapshot_id,
                DataSnapshotUpdate(
                    status="FAILED",
                    completed_at=self._now_utc(),
                    checksum=None,
                    notes="Snapshot build failed safely",
                ),
            )
        except Exception:
            raise SnapshotBuildError(SnapshotErrorCode.PERSISTENCE_FAILED) from None

    def _now_utc(self) -> datetime:
        value = self._clock.now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise SnapshotBuildError(SnapshotErrorCode.PERSISTENCE_FAILED)
        return value.astimezone(UTC)

    @staticmethod
    def _summary(item: SnapshotItemRecord) -> SnapshotItemSummary:
        return SnapshotItemSummary(
            item_id=item.id,
            provider_id=item.provider_id,
            category=item.category,
            source_record_type=item.source_record_type,
            source_record_id=item.source_record_id,
            checksum=item.checksum,
        )

    @staticmethod
    def _notes(warnings: tuple[str, ...]) -> str | None:
        if not warnings:
            return None
        canonical = SnapshotBuilder._canonical({"warnings": list(warnings)})
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"snapshot-warnings:v1:count={len(warnings)}:sha256={digest}"

    @staticmethod
    def _canonical(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _utc_text(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
