"""Unit contracts for the immutable as-of snapshot builder."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain import data_access
from stock_research_agent.domain.data_access import snapshots
from stock_research_agent.domain.data_access.enums import DataCategory
from stock_research_agent.domain.data_access.schemas import (
    CorporateActionRecord,
    DailyPriceBarRecord,
    DataSnapshotRecord,
    ProviderFinancialFactRecord,
    SnapshotItemRecord,
    SourceDocumentRecord,
)

SECURITY_ID = UUID("10000000-0000-0000-0000-000000000001")
PROVIDER_ID = UUID("20000000-0000-0000-0000-000000000001")
PROVIDER_TWO_ID = UUID("20000000-0000-0000-0000-000000000002")
PROVIDER_THREE_ID = UUID("20000000-0000-0000-0000-000000000003")
NOW = datetime(2026, 7, 10, 0, 30, tzinfo=UTC)


def test_snapshot_builder_module_exists() -> None:
    assert importlib.util.find_spec("stock_research_agent.domain.data_access.snapshots") is not None


def test_snapshot_builder_exposes_strict_internal_contracts() -> None:
    assert snapshots.SnapshotBuildRequest
    assert snapshots.SnapshotBuildResult
    assert snapshots.SnapshotItemSummary
    assert snapshots.SnapshotBuilder


def test_snapshot_contracts_are_available_from_data_access_package() -> None:
    assert data_access.SnapshotBuildRequest is snapshots.SnapshotBuildRequest
    assert data_access.SnapshotBuildResult is snapshots.SnapshotBuildResult
    assert data_access.SnapshotBuilder is snapshots.SnapshotBuilder
    assert data_access.SnapshotBuildError is snapshots.SnapshotBuildError


def _request(**overrides: object) -> snapshots.SnapshotBuildRequest:
    values: dict[str, object] = {
        "security_id": SECURITY_ID,
        "research_as_of_time": NOW,
        "snapshot_version": 1,
        "categories": (DataCategory.DAILY_PRICES,),
        "exchange_timezone": "America/New_York",
        "item_limit": 10,
    }
    values.update(overrides)
    return snapshots.SnapshotBuildRequest.model_validate(values)


def test_snapshot_request_normalizes_aware_cutoff_and_canonicalizes_categories() -> None:
    request = _request(
        research_as_of_time=NOW.astimezone(timezone(timedelta(hours=8))),
        categories=(DataCategory.FINANCIAL_FACTS, DataCategory.DAILY_PRICES),
    )

    assert request.research_as_of_time == NOW
    assert request.research_as_of_time.tzinfo is UTC
    assert request.categories == (
        DataCategory.DAILY_PRICES,
        DataCategory.FINANCIAL_FACTS,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("research_as_of_time", NOW.replace(tzinfo=None)),
        ("exchange_timezone", "Mars/Olympus_Mons"),
        ("categories", ()),
        ("categories", (DataCategory.DAILY_PRICES, DataCategory.DAILY_PRICES)),
        ("categories", (DataCategory.SOURCE_DOCUMENTS,)),
        ("provider_preference", (PROVIDER_ID, PROVIDER_ID)),
        ("item_limit", 0),
        ("item_limit", 100),
    ],
)
def test_snapshot_request_rejects_unsafe_or_ambiguous_inputs(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _request(**{field: value})


def test_snapshot_request_is_frozen_and_forbids_extra_fields() -> None:
    request = _request()
    with pytest.raises(ValidationError):
        request.snapshot_version = 2
    with pytest.raises(ValidationError):
        snapshots.SnapshotBuildRequest.model_validate(request.model_dump() | {"sql": "SELECT 1"})


def test_snapshot_result_contract_rejects_invalid_source_type_and_checksum() -> None:
    with pytest.raises(ValidationError):
        snapshots.SnapshotItemSummary(
            item_id=UUID(int=1),
            provider_id=PROVIDER_ID,
            category=DataCategory.DAILY_PRICES,
            source_record_type="raw_payloads",
            source_record_id=UUID(int=2),
            checksum="not-a-checksum",
        )


class FixedClock:
    def now(self) -> datetime:
        return NOW + timedelta(minutes=1)


def _bar(
    record_id: int,
    *,
    provider_id: UUID = PROVIDER_ID,
    trading_date: datetime | None = None,
    published_at: datetime | None = NOW - timedelta(minutes=2),
    retrieved_at: datetime = NOW - timedelta(minutes=1),
) -> DailyPriceBarRecord:
    return DailyPriceBarRecord(
        id=UUID(int=record_id),
        security_id=SECURITY_ID,
        provider_id=provider_id,
        source_payload_id=UUID(int=10_000 + record_id),
        provider_symbol="MU",
        trading_date=(trading_date or NOW).date(),
        close="10.25",
        currency_code="USD",
        source_published_at=published_at,
        retrieved_at=retrieved_at,
        created_at=retrieved_at,
    )


def _action(record_id: int, *, provider_id: UUID = PROVIDER_ID) -> CorporateActionRecord:
    return CorporateActionRecord(
        id=UUID(int=record_id),
        security_id=SECURITY_ID,
        provider_id=provider_id,
        source_payload_id=UUID(int=10_000 + record_id),
        action_type="CASH_DIVIDEND",
        status="CONFIRMED",
        source_published_at=NOW - timedelta(minutes=2),
        retrieved_at=NOW - timedelta(minutes=1),
        created_at=NOW - timedelta(minutes=1),
    )


def _fact(record_id: int, *, provider_id: UUID = PROVIDER_ID) -> ProviderFinancialFactRecord:
    return ProviderFinancialFactRecord(
        id=UUID(int=record_id),
        security_id=SECURITY_ID,
        provider_id=provider_id,
        source_payload_id=UUID(int=10_000 + record_id),
        statement_type="OTHER",
        provider_concept="raw:Revenue",
        dimensions={},
        source_published_at=NOW - timedelta(minutes=2),
        retrieved_at=NOW - timedelta(minutes=1),
        created_at=NOW - timedelta(minutes=1),
    )


def _document(record_id: int, *, provider_id: UUID = PROVIDER_ID) -> SourceDocumentRecord:
    instant = NOW - timedelta(minutes=1)
    return SourceDocumentRecord(
        id=UUID(int=record_id),
        security_id=SECURITY_ID,
        provider_id=provider_id,
        source_payload_id=UUID(int=10_000 + record_id),
        provider_document_id=f"doc-{record_id}",
        document_type="OTHER",
        title="Safe filing metadata",
        form_type=None,
        accession_number=None,
        announcement_id=None,
        period_end=None,
        filed_at=None,
        published_at=NOW - timedelta(minutes=2),
        source_url="https://example.invalid/document",
        primary_document_name=None,
        mime_type=None,
        checksum=None,
        byte_size=None,
        document_status="METADATA_ONLY",
        retrieved_at=instant,
        created_at=instant,
        updated_at=instant,
    )


class FakeSnapshotRepository:
    def __init__(self) -> None:
        self.records: dict[DataCategory, list[object]] = {
            DataCategory.DAILY_PRICES: [],
            DataCategory.CORPORATE_ACTIONS: [],
            DataCategory.FINANCIAL_FACTS: [],
            DataCategory.FILING_METADATA: [],
        }
        self.snapshots: dict[tuple[UUID, datetime, int], DataSnapshotRecord] = {}
        self.items: dict[UUID, list[SnapshotItemRecord]] = {}
        self.candidate_calls: list[tuple[DataCategory, int, UUID | None, object]] = []
        self.fail_add_item = False
        self.fail_terminal_updates = 0
        self.fail_selection = False

    def get_or_create_snapshot(self, value: object) -> tuple[DataSnapshotRecord, bool]:
        values = value.model_dump(mode="python")
        key = (
            values["security_id"],
            values["research_as_of_time"],
            values["snapshot_version"],
        )
        existing = self.snapshots.get(key)
        if existing is not None:
            return existing, False
        record = DataSnapshotRecord(
            id=UUID(int=50_000 + values["snapshot_version"]),
            created_at=NOW,
            **values,
        )
        self.snapshots[key] = record
        self.items[record.id] = []
        return record, True

    @contextmanager
    def snapshot_attempt(self) -> Iterator[None]:
        item_backup = {key: list(value) for key, value in self.items.items()}
        snapshot_backup = dict(self.snapshots)
        try:
            yield
        except Exception:
            self.items = item_backup
            self.snapshots = snapshot_backup
            raise

    def update_snapshot(self, snapshot_id: UUID, value: object) -> DataSnapshotRecord:
        if self.fail_terminal_updates:
            self.fail_terminal_updates -= 1
            raise RuntimeError("postgresql://user:SECRET@host/db SQL /private/item")
        key, current = next(
            (key, record) for key, record in self.snapshots.items() if record.id == snapshot_id
        )
        updated = DataSnapshotRecord.model_validate(
            current.model_dump(mode="python") | value.model_dump(mode="python")
        )
        self.snapshots[key] = updated
        return updated

    def add_snapshot_item(self, value: object) -> SnapshotItemRecord:
        if self.fail_add_item:
            raise RuntimeError("postgresql://user:SECRET@host/db SQL /private/item")
        record = SnapshotItemRecord(
            id=UUID(int=60_000 + sum(len(rows) for rows in self.items.values())),
            created_at=NOW,
            **value.model_dump(mode="python"),
        )
        self.items[record.snapshot_id].append(record)
        return record

    def list_snapshot_items(self, snapshot_id: UUID, limit: int) -> tuple[SnapshotItemRecord, ...]:
        return tuple(self.items[snapshot_id][:limit])

    def list_snapshot_items_for_replay(self, snapshot_id: UUID) -> tuple[SnapshotItemRecord, ...]:
        rows = tuple(self.items[snapshot_id])
        if len(rows) > 396:
            raise RuntimeError("snapshot replay item limit exceeded")
        return rows

    def _candidates(
        self,
        category: DataCategory,
        limit: int,
        provider_id: UUID | None,
        marker: object = None,
    ) -> tuple[object, ...]:
        if self.fail_selection:
            raise RuntimeError("postgresql://user:SECRET@host/db SQL /private/selection")
        self.candidate_calls.append((category, limit, provider_id, marker))
        rows = self.records[category]
        if provider_id is not None:
            rows = [row for row in rows if row.provider_id == provider_id]
        return tuple(rows[:limit])

    def list_daily_history(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        local_trading_date: object,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[object, ...]:
        assert security_id == SECURITY_ID
        return self._candidates(DataCategory.DAILY_PRICES, limit, provider_id, local_trading_date)

    def list_corporate_actions(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[object, ...]:
        return self._candidates(DataCategory.CORPORATE_ACTIONS, limit, provider_id)

    def list_financial_facts(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[object, ...]:
        return self._candidates(DataCategory.FINANCIAL_FACTS, limit, provider_id)

    def list_source_documents(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[object, ...]:
        return self._candidates(DataCategory.FILING_METADATA, limit, provider_id)


def _builder(repository: FakeSnapshotRepository) -> snapshots.SnapshotBuilder:
    return snapshots.SnapshotBuilder(repository, clock=FixedClock())


def test_daily_prices_use_exchange_local_calendar_date_near_utc_boundary() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(2, trading_date=datetime(2026, 7, 10, tzinfo=UTC)),
        _bar(1, trading_date=datetime(2026, 7, 9, tzinfo=UTC)),
    ]

    result = _builder(repository).build(_request())

    assert result.status == "COMPLETE"
    assert [item.source_record_id for item in result.items] == [UUID(int=1)]
    assert repository.candidate_calls[0][3].isoformat() == "2026-07-09"


def test_known_future_publication_and_retrieval_are_excluded() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(
            1,
            trading_date=datetime(2026, 7, 9, tzinfo=UTC),
            published_at=NOW + timedelta(seconds=1),
        ),
        _bar(
            2,
            trading_date=datetime(2026, 7, 9, tzinfo=UTC),
            retrieved_at=NOW + timedelta(seconds=1),
        ),
    ]

    result = _builder(repository).build(_request())

    assert result.status == "PARTIAL"
    assert result.items == ()
    assert result.warnings == ("MISSING_CATEGORY:DAILY_PRICES",)


def test_unknown_publication_is_included_but_forces_partial() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(1, trading_date=datetime(2026, 7, 9, tzinfo=UTC), published_at=None)
    ]

    result = _builder(repository).build(_request())

    assert result.status == "PARTIAL"
    assert len(result.items) == 1
    assert result.warnings == (
        "UNKNOWN_PUBLICATION:DAILY_PRICES:daily_price_bars:00000000-0000-0000-0000-000000000001",
    )


def test_missing_requested_category_is_partial_without_fake_item() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(1, trading_date=datetime(2026, 7, 9, tzinfo=UTC))
    ]
    request = _request(categories=(DataCategory.DAILY_PRICES, DataCategory.FINANCIAL_FACTS))

    result = _builder(repository).build(request)

    assert result.status == "PARTIAL"
    assert [item.category for item in result.items] == [DataCategory.DAILY_PRICES]
    assert result.warnings == ("MISSING_CATEGORY:FINANCIAL_FACTS",)


def test_all_requested_categories_known_are_complete_and_canonically_ordered() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(4, trading_date=datetime(2026, 7, 9, tzinfo=UTC))
    ]
    repository.records[DataCategory.CORPORATE_ACTIONS] = [_action(3)]
    repository.records[DataCategory.FINANCIAL_FACTS] = [_fact(2)]
    repository.records[DataCategory.FILING_METADATA] = [_document(1)]
    request = _request(
        categories=(
            DataCategory.FILING_METADATA,
            DataCategory.FINANCIAL_FACTS,
            DataCategory.DAILY_PRICES,
            DataCategory.CORPORATE_ACTIONS,
        )
    )

    result = _builder(repository).build(request)

    assert result.status == "COMPLETE"
    assert result.warnings == ()
    assert [(item.category.value, item.source_record_type) for item in result.items] == sorted(
        (item.category.value, item.source_record_type) for item in result.items
    )


def test_provider_preference_chooses_highest_ranked_available_and_never_falls_back() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(1, provider_id=PROVIDER_THREE_ID, trading_date=datetime(2026, 7, 9, tzinfo=UTC)),
        _bar(2, provider_id=PROVIDER_TWO_ID, trading_date=datetime(2026, 7, 9, tzinfo=UTC)),
    ]
    preferred = _request(provider_preference=(PROVIDER_ID, PROVIDER_TWO_ID))

    result = _builder(repository).build(preferred)

    assert result.status == "COMPLETE"
    assert [item.provider_id for item in result.items] == [PROVIDER_TWO_ID]
    no_match = _builder(FakeSnapshotRepository()).build(
        preferred.model_copy(update={"snapshot_version": 2})
    )
    assert no_match.status == "PARTIAL"
    assert no_match.warnings == (
        "NO_PREFERRED_PROVIDER:DAILY_PRICES",
        "MISSING_CATEGORY:DAILY_PRICES",
    )


def test_item_and_snapshot_checksums_are_exact_stable_and_replay_equal() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(1, trading_date=datetime(2026, 7, 9, tzinfo=UTC))
    ]
    builder = _builder(repository)
    request = _request()

    first = builder.build(request)
    replay = builder.build(request)

    assert replay == first
    persisted = repository.items[first.snapshot.id][0]
    assert (
        persisted.checksum == hashlib.sha256(persisted.checksum_input.encode("utf-8")).hexdigest()
    )
    assert len(first.checksum) == 64
    assert first.checksum == first.snapshot.checksum
    assert "created_at" not in persisted.checksum_input
    assert str(first.snapshot.id) not in persisted.checksum_input


def test_replay_returns_all_items_above_general_query_limit() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(record_id, trading_date=datetime(2026, 7, 9, tzinfo=UTC)) for record_id in range(1, 61)
    ]
    repository.records[DataCategory.FINANCIAL_FACTS] = [
        _fact(record_id) for record_id in range(101, 161)
    ]
    builder = _builder(repository)
    request = _request(
        categories=(DataCategory.DAILY_PRICES, DataCategory.FINANCIAL_FACTS),
        item_limit=60,
    )

    first = builder.build(request)
    replay = builder.build(request)

    assert len(first.items) == 120
    assert replay == first


def test_changed_evidence_same_version_conflicts_and_new_version_succeeds() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(1, trading_date=datetime(2026, 7, 9, tzinfo=UTC))
    ]
    builder = _builder(repository)
    first = builder.build(_request())
    repository.records[DataCategory.DAILY_PRICES].append(
        _bar(2, trading_date=datetime(2026, 7, 9, tzinfo=UTC))
    )

    with pytest.raises(snapshots.SnapshotBuildError) as captured:
        builder.build(_request())
    assert captured.value.code is snapshots.SnapshotErrorCode.VERSION_CONFLICT
    second = builder.build(_request(snapshot_version=2))
    assert second.snapshot.id != first.snapshot.id
    assert second.checksum != first.checksum


def test_bounded_candidates_and_truncation_can_never_complete() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(1, trading_date=datetime(2026, 7, 9, tzinfo=UTC)),
        _bar(2, trading_date=datetime(2026, 7, 9, tzinfo=UTC)),
    ]

    result = _builder(repository).build(_request(item_limit=1))

    assert result.status == "PARTIAL"
    assert len(result.items) == 1
    assert result.warnings == ("TRUNCATED_CATEGORY:DAILY_PRICES",)
    assert repository.candidate_calls[0][1] == 2


def test_many_unknown_publication_warnings_keep_persisted_notes_bounded() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(
            record_id,
            trading_date=datetime(2026, 7, 9, tzinfo=UTC),
            published_at=None,
        )
        for record_id in range(1, 100)
    ]

    result = _builder(repository).build(_request(item_limit=99))

    assert result.status == "PARTIAL"
    assert len(result.items) == len(result.warnings) == 99
    assert result.snapshot.notes is not None
    assert len(result.snapshot.notes) <= 1024


def test_projection_and_terminal_update_failures_are_typed_safe_and_leave_no_items() -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(1, trading_date=datetime(2026, 7, 9, tzinfo=UTC))
    ]
    repository.fail_add_item = True

    with pytest.raises(snapshots.SnapshotBuildError) as captured:
        _builder(repository).build(_request())

    error = captured.value
    assert error.code is snapshots.SnapshotErrorCode.BUILD_FAILED
    assert str(error) == "Snapshot build failed safely"
    assert all(snapshot.status == "FAILED" for snapshot in repository.snapshots.values())
    assert all(snapshot.checksum is None for snapshot in repository.snapshots.values())
    assert all(items == [] for items in repository.items.values())
    for sentinel in ("SECRET", "postgresql", " SQL ", "/private"):
        assert sentinel not in str(error)
        assert sentinel not in repr(error)

    terminal_failure = FakeSnapshotRepository()
    terminal_failure.records[DataCategory.DAILY_PRICES] = repository.records[
        DataCategory.DAILY_PRICES
    ]
    terminal_failure.fail_add_item = True
    terminal_failure.fail_terminal_updates = 1
    with pytest.raises(snapshots.SnapshotBuildError) as terminal_captured:
        _builder(terminal_failure).build(_request(snapshot_version=2))
    assert terminal_captured.value.code is snapshots.SnapshotErrorCode.PERSISTENCE_FAILED
    assert str(terminal_captured.value) == "Snapshot persistence failed safely"


def _assert_safe_snapshot_error(
    error: snapshots.SnapshotBuildError,
    code: snapshots.SnapshotErrorCode,
    message: str,
) -> None:
    assert error.code is code
    assert str(error) == message
    for sentinel in ("SECRET", "postgresql", " SQL ", "/private", "payload"):
        assert sentinel not in str(error)
        assert sentinel not in repr(error)
    assert error.__cause__ is None


def test_selection_failure_creates_safe_failed_snapshot_without_items() -> None:
    repository = FakeSnapshotRepository()
    repository.fail_selection = True

    with pytest.raises(snapshots.SnapshotBuildError) as captured:
        _builder(repository).build(_request())

    _assert_safe_snapshot_error(
        captured.value,
        snapshots.SnapshotErrorCode.BUILD_FAILED,
        "Snapshot build failed safely",
    )
    assert len(repository.snapshots) == 1
    assert all(snapshot.status == "FAILED" for snapshot in repository.snapshots.values())
    assert all(snapshot.checksum is None for snapshot in repository.snapshots.values())
    assert all(items == [] for items in repository.items.values())


@pytest.mark.parametrize("failure_stage", ("projection", "checksum", "result"))
def test_post_selection_failures_are_safe_failed_and_atomic(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(1, trading_date=datetime(2026, 7, 9, tzinfo=UTC))
    ]

    def fail(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("postgresql://user:SECRET@host/db SQL /private/payload")

    if failure_stage == "projection":
        monkeypatch.setattr(snapshots.SnapshotBuilder, "_item_write", fail)
    elif failure_stage == "checksum":
        monkeypatch.setattr(snapshots.SnapshotBuilder, "_snapshot_checksum", fail)
    else:
        monkeypatch.setattr(snapshots, "SnapshotBuildResult", fail)

    with pytest.raises(snapshots.SnapshotBuildError) as captured:
        _builder(repository).build(_request())

    _assert_safe_snapshot_error(
        captured.value,
        snapshots.SnapshotErrorCode.BUILD_FAILED,
        "Snapshot build failed safely",
    )
    assert all(snapshot.status == "FAILED" for snapshot in repository.snapshots.values())
    assert all(snapshot.checksum is None for snapshot in repository.snapshots.values())
    assert all(items == [] for items in repository.items.values())


def test_failed_terminal_update_is_safe_persistence_error() -> None:
    repository = FakeSnapshotRepository()
    repository.fail_selection = True
    repository.fail_terminal_updates = 1

    with pytest.raises(snapshots.SnapshotBuildError) as captured:
        _builder(repository).build(_request())

    _assert_safe_snapshot_error(
        captured.value,
        snapshots.SnapshotErrorCode.PERSISTENCE_FAILED,
        "Snapshot persistence failed safely",
    )
    assert all(snapshot.status == "BUILDING" for snapshot in repository.snapshots.values())
    assert all(items == [] for items in repository.items.values())


@pytest.mark.parametrize("failure_stage", ("selection", "projection", "checksum", "result"))
def test_terminal_replay_failure_is_safe_and_never_mutates_terminal(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(1, trading_date=datetime(2026, 7, 9, tzinfo=UTC))
    ]
    builder = _builder(repository)
    first = builder.build(_request())
    terminal_snapshot = repository.snapshots[(SECURITY_ID, NOW, 1)]
    terminal_items = tuple(repository.items[first.snapshot.id])

    def fail(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("postgresql://user:SECRET@host/db SQL /private/payload")

    if failure_stage == "selection":
        repository.fail_selection = True
    elif failure_stage == "projection":
        monkeypatch.setattr(snapshots.SnapshotBuilder, "_item_write", fail)
    elif failure_stage == "checksum":
        monkeypatch.setattr(snapshots.SnapshotBuilder, "_snapshot_checksum", fail)
    else:
        monkeypatch.setattr(snapshots, "SnapshotBuildResult", fail)

    with pytest.raises(snapshots.SnapshotBuildError) as captured:
        builder.build(_request())

    _assert_safe_snapshot_error(
        captured.value,
        snapshots.SnapshotErrorCode.BUILD_FAILED,
        "Snapshot build failed safely",
    )
    assert repository.snapshots[(SECURITY_ID, NOW, 1)] == terminal_snapshot
    assert tuple(repository.items[first.snapshot.id]) == terminal_items


@pytest.mark.parametrize("mismatch", ("count", "order", "checksum"))
def test_terminal_replay_detects_persisted_item_mismatch_without_mutation(
    mismatch: str,
) -> None:
    repository = FakeSnapshotRepository()
    repository.records[DataCategory.DAILY_PRICES] = [
        _bar(record_id, trading_date=datetime(2026, 7, 9, tzinfo=UTC)) for record_id in (1, 2)
    ]
    builder = _builder(repository)
    first = builder.build(_request())
    terminal_snapshot = repository.snapshots[(SECURITY_ID, NOW, 1)]
    stored = repository.items[first.snapshot.id]
    if mismatch == "count":
        stored.pop()
    elif mismatch == "order":
        stored.reverse()
    else:
        stored[0] = stored[0].model_copy(update={"checksum": "0" * 64})
    mismatched_items = tuple(stored)

    with pytest.raises(snapshots.SnapshotBuildError) as captured:
        builder.build(_request())

    _assert_safe_snapshot_error(
        captured.value,
        snapshots.SnapshotErrorCode.VERSION_CONFLICT,
        "Snapshot version conflicts with existing evidence",
    )
    assert repository.snapshots[(SECURITY_ID, NOW, 1)] == terminal_snapshot
    assert tuple(repository.items[first.snapshot.id]) == mismatched_items


def test_snapshot_domain_has_no_framework_storage_network_or_session_dependency() -> None:
    source = Path(inspect.getfile(snapshots)).read_text(encoding="utf-8")
    forbidden = (
        "sqlalchemy",
        "fastapi",
        "typer",
        "BlobStorage",
        "ProviderRegistry",
        "socket",
        "Session(",
        ".commit(",
        ".rollback(",
        ".close(",
    )
    assert all(name not in source for name in forbidden)
