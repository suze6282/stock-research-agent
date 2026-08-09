from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import BaseModel

from stock_research_agent.domain.data_access.enums import DataCategory
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.data_access.schemas import (
    CorporateActionRecord,
    DailyPriceBarRecord,
    DataSnapshotRecord,
    ProviderFinancialFactRecord,
    ProviderProvenanceRecord,
    SnapshotEvidenceAggregateRecord,
    SnapshotItemRecord,
    SourceDocumentRecord,
)
from stock_research_agent.tools.registry import (
    ToolErrorCode,
    ToolRegistryError,
    create_tool_registry,
)

SECURITY_ID = UUID("40000000-0000-0000-0000-000000000001")
OTHER_SECURITY_ID = UUID("40000000-0000-0000-0000-000000000002")
FIXTURE_PROVIDER_ID = UUID("50000000-0000-0000-0000-000000000001")
LIVE_PROVIDER_ID = UUID("50000000-0000-0000-0000-000000000002")
MISSING_PROVIDER_ID = UUID("50000000-0000-0000-0000-000000000003")
PAYLOAD_ID = UUID("80000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("a0000000-0000-0000-0000-000000000001")
AS_OF = datetime(2026, 7, 10, 20, tzinfo=UTC)
OLD_RETRIEVED = AS_OF - timedelta(hours=2)
NEW_RETRIEVED = AS_OF - timedelta(hours=1)


def _bar(
    record_id: int,
    *,
    close: str,
    trading_date: date,
    provider_id: UUID = FIXTURE_PROVIDER_ID,
    security_id: UUID = SECURITY_ID,
    retrieved_at: datetime = OLD_RETRIEVED,
    published: bool = True,
) -> DailyPriceBarRecord:
    return DailyPriceBarRecord(
        id=UUID(int=record_id),
        security_id=security_id,
        provider_id=provider_id,
        source_payload_id=PAYLOAD_ID,
        provider_symbol="MU",
        trading_date=trading_date,
        market_timestamp=None,
        open=Decimal(close) - 1,
        high=Decimal(close) + 1,
        low=Decimal(close) - 2,
        close=Decimal(close),
        volume=100,
        currency_code="USD",
        adjustment_type="UNADJUSTED",
        provider_adjusted_close=None,
        source_published_at=retrieved_at if published else None,
        retrieved_at=retrieved_at,
        created_at=retrieved_at,
    )


def _action(record_id: int, provider_id: UUID = FIXTURE_PROVIDER_ID) -> CorporateActionRecord:
    return CorporateActionRecord(
        id=UUID(int=record_id),
        security_id=SECURITY_ID,
        provider_id=provider_id,
        source_payload_id=PAYLOAD_ID,
        provider_action_id="action-1",
        action_type="CASH_DIVIDEND",
        announcement_date=date(2026, 7, 1),
        ex_date=date(2026, 7, 8),
        record_date=date(2026, 7, 9),
        payment_date=date(2026, 7, 20),
        cash_amount=Decimal("0.125"),
        currency_code="USD",
        ratio_numerator=None,
        ratio_denominator=None,
        status="CONFIRMED",
        source_published_at=OLD_RETRIEVED,
        retrieved_at=OLD_RETRIEVED,
        created_at=OLD_RETRIEVED,
    )


def _fact(record_id: int, provider_id: UUID = FIXTURE_PROVIDER_ID) -> ProviderFinancialFactRecord:
    return ProviderFinancialFactRecord(
        id=UUID(int=record_id),
        security_id=SECURITY_ID,
        provider_id=provider_id,
        source_payload_id=PAYLOAD_ID,
        document_id=UUID(int=50),
        statement_type="INCOME_STATEMENT",
        provider_concept="us-gaap:Revenue",
        reported_label="Revenue",
        taxonomy="us-gaap",
        context_id="ctx-1",
        dimensions={"segment": "reported"},
        value=Decimal("1234567890.123456789012"),
        unit="USD",
        currency_code="USD",
        fiscal_year=2026,
        fiscal_quarter=2,
        fiscal_period="Q2",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
        instant_date=None,
        filed_at=OLD_RETRIEVED,
        source_published_at=OLD_RETRIEVED,
        form_type="10-Q",
        is_annual=False,
        is_cumulative=True,
        is_audited=False,
        is_restated=False,
        provider_record_id="fact-1",
        retrieved_at=OLD_RETRIEVED,
        created_at=OLD_RETRIEVED,
    )


def _document(record_id: int, provider_id: UUID = FIXTURE_PROVIDER_ID) -> SourceDocumentRecord:
    return SourceDocumentRecord(
        id=UUID(int=record_id),
        security_id=SECURITY_ID,
        provider_id=provider_id,
        source_payload_id=PAYLOAD_ID,
        provider_document_id="document-1",
        document_type="SEC_10_Q",
        title="Quarterly report",
        form_type="10-Q",
        accession_number="0001",
        announcement_id=None,
        period_end=date(2026, 6, 30),
        filed_at=OLD_RETRIEVED,
        published_at=OLD_RETRIEVED,
        source_url="https://www.sec.gov/example",
        primary_document_name="example.htm",
        mime_type="text/html",
        checksum="c" * 64,
        byte_size=1234,
        document_status="AVAILABLE",
        retrieved_at=OLD_RETRIEVED,
        created_at=OLD_RETRIEVED,
        updated_at=OLD_RETRIEVED,
    )


def _snapshot(
    *,
    security_id: UUID = SECURITY_ID,
    status: str = "COMPLETE",
) -> DataSnapshotRecord:
    return DataSnapshotRecord(
        id=SNAPSHOT_ID,
        security_id=security_id,
        research_as_of_time=AS_OF,
        snapshot_version=1,
        status=status,
        completed_at=AS_OF if status != "BUILDING" else None,
        checksum=None if status in {"BUILDING", "FAILED"} else "d" * 64,
        formula_version="raw-data-v1",
        notes=None,
        created_at=AS_OF,
    )


def _item(
    item_id: int,
    category: DataCategory,
    source_type: str,
    source_id: UUID,
    provider_id: UUID = FIXTURE_PROVIDER_ID,
) -> SnapshotItemRecord:
    return SnapshotItemRecord(
        id=UUID(int=item_id),
        snapshot_id=SNAPSHOT_ID,
        provider_id=provider_id,
        category=category,
        source_record_type=source_type,
        source_record_id=source_id,
        source_published_at=OLD_RETRIEVED,
        retrieved_at=OLD_RETRIEVED,
        checksum_input="safe-descriptor",
        checksum="e" * 64,
        created_at=AS_OF,
    )


class FakeReadRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.providers = {
            FIXTURE_PROVIDER_ID: ProviderProvenanceRecord(
                id=FIXTURE_PROVIDER_ID,
                code="FIXTURE_STAGE1",
                provider_type="FIXTURE",
                status="EXPERIMENTAL",
                terms_status="NEEDS_REVIEW",
            ),
            LIVE_PROVIDER_ID: ProviderProvenanceRecord(
                id=LIVE_PROVIDER_ID,
                code="LIVE_MARKET",
                provider_type="MARKET_DATA",
                status="APPROVED",
                terms_status="VERIFIED",
            ),
        }
        self.bars = (
            _bar(11, close="10.25", trading_date=date(2026, 7, 9)),
            _bar(
                12,
                close="99.99",
                trading_date=date(2026, 7, 10),
                retrieved_at=NEW_RETRIEVED,
            ),
        )
        self.actions = (_action(21),)
        self.facts = (_fact(31),)
        self.documents = (_document(41),)
        self.snapshot_record: DataSnapshotRecord | None = _snapshot()
        self.items = (
            _item(101, DataCategory.DAILY_PRICES, "daily_price_bars", UUID(int=11)),
            _item(102, DataCategory.CORPORATE_ACTIONS, "corporate_actions", UUID(int=21)),
            _item(
                103,
                DataCategory.FINANCIAL_FACTS,
                "provider_financial_facts",
                UUID(int=31),
            ),
            _item(104, DataCategory.FILING_METADATA, "source_documents", UUID(int=41)),
        )
        self.fail_reads = False
        self.fail_provider_provenance = False
        self.fail_snapshot_items = False
        self.fail_snapshot_aggregate = False
        self.aggregate_record: SnapshotEvidenceAggregateRecord | None = (
            SnapshotEvidenceAggregateRecord(
                snapshot_id=SNAPSHOT_ID,
                provider_ids=(FIXTURE_PROVIDER_ID,),
                latest_retrieved_at=OLD_RETRIEVED,
                item_count=4,
            )
        )

    def _check(self, name: str) -> None:
        if self.fail_reads:
            raise RuntimeError(f"unsafe repository error from {name}: SECRET_SENTINEL")

    def get_latest_close(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        local_trading_date: date | None,
    ) -> DailyPriceBarRecord | None:
        self._check("latest")
        self.calls.append(("latest_close", security_id))
        return self.bars[1]

    def list_daily_history(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        local_trading_date: date | None,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[DailyPriceBarRecord, ...]:
        self._check("history")
        self.calls.append(("history", limit))
        return self.bars[:limit]

    def list_corporate_actions(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[CorporateActionRecord, ...]:
        self._check("actions")
        self.calls.append(("actions", limit))
        return self.actions[:limit]

    def list_financial_facts(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[ProviderFinancialFactRecord, ...]:
        self._check("facts")
        self.calls.append(("facts", limit))
        return self.facts[:limit]

    def list_source_documents(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[SourceDocumentRecord, ...]:
        self._check("documents")
        self.calls.append(("documents", limit))
        return self.documents[:limit]

    def get_source_document_metadata(
        self,
        document_id: UUID,
        security_id: UUID,
        research_as_of_time: datetime,
    ) -> SourceDocumentRecord | None:
        self._check("document_metadata")
        self.calls.append(("document_metadata", document_id))
        return next(
            (
                value
                for value in self.documents
                if value.id == document_id and value.security_id == security_id
            ),
            None,
        )

    def get_snapshot(self, snapshot_id: UUID) -> DataSnapshotRecord | None:
        self._check("snapshot")
        self.calls.append(("snapshot", snapshot_id))
        return self.snapshot_record if snapshot_id == SNAPSHOT_ID else None

    def get_latest_eligible_snapshot(
        self, security_id: UUID, research_as_of_time: datetime
    ) -> DataSnapshotRecord | None:
        return None

    def list_snapshot_items(self, snapshot_id: UUID, limit: int) -> tuple[SnapshotItemRecord, ...]:
        self._check("snapshot_items")
        if self.fail_snapshot_items:
            raise RuntimeError("unsafe snapshot item failure: SECRET_SENTINEL")
        self.calls.append(("snapshot_items", limit))
        return self.items[:limit] if snapshot_id == SNAPSHOT_ID else ()

    def get_snapshot_evidence_aggregate(
        self, snapshot_id: UUID
    ) -> SnapshotEvidenceAggregateRecord | None:
        self._check("snapshot_evidence_aggregate")
        if self.fail_snapshot_aggregate:
            raise RuntimeError("unsafe snapshot aggregate failure: SECRET_SENTINEL")
        self.calls.append(("snapshot_evidence_aggregate", snapshot_id))
        return self.aggregate_record if snapshot_id == SNAPSHOT_ID else None

    def list_snapshot_items_by_category(
        self,
        snapshot_id: UUID,
        category: DataCategory,
        limit: int,
    ) -> tuple[SnapshotItemRecord, ...]:
        self._check("snapshot_category")
        self.calls.append(("snapshot_category", category))
        return tuple(
            item
            for item in self.items
            if item.snapshot_id == snapshot_id and item.category is category
        )[:limit]

    def list_daily_prices_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> tuple[DailyPriceBarRecord, ...]:
        self._check("bars_by_ids")
        self.calls.append(("bars_by_ids", source_ids))
        return tuple(
            record
            for record in self.bars
            if record.security_id == security_id and record.id in source_ids
        )

    def list_corporate_actions_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> tuple[CorporateActionRecord, ...]:
        self._check("actions_by_ids")
        self.calls.append(("actions_by_ids", source_ids))
        return tuple(record for record in self.actions if record.id in source_ids)

    def list_financial_facts_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> tuple[ProviderFinancialFactRecord, ...]:
        self._check("facts_by_ids")
        self.calls.append(("facts_by_ids", source_ids))
        return tuple(record for record in self.facts if record.id in source_ids)

    def list_source_documents_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> tuple[SourceDocumentRecord, ...]:
        self._check("documents_by_ids")
        self.calls.append(("documents_by_ids", source_ids))
        return tuple(record for record in self.documents if record.id in source_ids)

    def list_provider_provenance(
        self, provider_ids: tuple[UUID, ...]
    ) -> tuple[ProviderProvenanceRecord, ...]:
        self._check("provider_provenance")
        if self.fail_provider_provenance:
            raise RuntimeError("unsafe provenance failure: SECRET_SENTINEL")
        self.calls.append(("provider_provenance", provider_ids))
        return tuple(self.providers[value] for value in provider_ids if value in self.providers)

    def list_providers(self, limit: int) -> tuple[()]:
        return ()

    def get_provider(self, code: str) -> None:
        return None

    def get_active_mapping(self, security_id: UUID, provider_code: str, as_of: date) -> None:
        return None

    def list_snapshot_items_for_replay(self, snapshot_id: UUID) -> tuple[SnapshotItemRecord, ...]:
        raise AssertionError("builder-only replay port must never be called")


def _registry(repository: FakeReadRepository | None = None):
    repository = repository or FakeReadRepository()
    return create_tool_registry(DataAccessQueryService(repository)), repository


def _execute(
    name: str,
    payload: dict[str, object],
    repository: FakeReadRepository | None = None,
) -> tuple[BaseModel, FakeReadRepository]:
    registry, repository = _registry(repository)
    return registry.execute(name, "1.0.0", payload), repository


@pytest.mark.parametrize(
    ("name", "payload", "expected_count"),
    (
        (
            "get_latest_close",
            {"security_id": SECURITY_ID, "research_as_of_time": AS_OF},
            1,
        ),
        (
            "get_daily_price_history",
            {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 2},
            2,
        ),
        (
            "get_corporate_actions",
            {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 10},
            1,
        ),
        (
            "get_reported_financial_facts",
            {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 10},
            1,
        ),
        (
            "list_source_documents",
            {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 10},
            1,
        ),
        (
            "get_source_document_metadata",
            {
                "document_id": UUID(int=41),
                "security_id": SECURITY_ID,
                "research_as_of_time": AS_OF,
            },
            1,
        ),
        ("get_data_snapshot", {"snapshot_id": SNAPSHOT_ID}, 1),
        ("list_snapshot_items", {"snapshot_id": SNAPSHOT_ID, "limit": 10}, 4),
    ),
)
def test_all_eight_tools_return_strict_human_and_json_serializable_envelopes(
    name: str, payload: dict[str, object], expected_count: int
) -> None:
    result, _repository = _execute(name, payload)

    assert result.tool_name == name
    assert result.tool_version == "1.0.0"
    assert result.quality.record_count == expected_count
    assert len(result.data) == expected_count
    assert isinstance(result.model_dump(mode="python"), dict)
    assert json.loads(result.model_dump_json())["tool_name"] == name


@pytest.mark.parametrize(
    "payload",
    (
        {"security_id": SECURITY_ID},
        {
            "security_id": SECURITY_ID,
            "snapshot_id": SNAPSHOT_ID,
            "research_as_of_time": AS_OF,
        },
        {
            "security_id": SECURITY_ID,
            "research_as_of_time": datetime(2026, 7, 10, 20),
        },
        {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 0},
        {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 101},
        {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "sort": "desc"},
    ),
)
def test_scope_limit_and_extra_control_validation_is_strict_and_non_echoing(
    payload: dict[str, object],
) -> None:
    registry, _repository = _registry()

    with pytest.raises(ToolRegistryError) as captured:
        registry.execute("get_daily_price_history", "1.0.0", payload)

    assert captured.value.code is ToolErrorCode.INVALID_INPUT
    assert str(captured.value) == "Tool input was invalid"


def test_json_parse_layer_accepts_uuid_and_aware_time_without_weakening_python_contract() -> None:
    registry, _repository = _registry()
    json_payload = json.dumps(
        {
            "security_id": str(SECURITY_ID),
            "research_as_of_time": AS_OF.isoformat(),
            "limit": 1,
        }
    )

    result = registry.execute("get_daily_price_history", "1.0.0", json_payload)
    assert result.quality.record_count == 1

    with pytest.raises(ToolRegistryError) as captured:
        registry.execute(
            "get_daily_price_history",
            "1.0.0",
            {
                "security_id": str(SECURITY_ID),
                "research_as_of_time": AS_OF.isoformat(),
                "limit": 1,
            },
        )
    assert captured.value.code is ToolErrorCode.INVALID_INPUT


def test_snapshot_scope_reads_only_exact_captured_ids_and_never_leaks_newer_records() -> None:
    result, repository = _execute(
        "get_daily_price_history",
        {"security_id": SECURITY_ID, "snapshot_id": SNAPSHOT_ID, "limit": 10},
    )

    assert [record.id for record in result.data] == [UUID(int=11)]
    assert [record.close for record in result.data] == [Decimal("10.25")]
    assert result.source_record_ids == (UUID(int=11),)
    assert result.snapshot_id == SNAPSHOT_ID
    assert result.research_as_of_time is None
    assert ("bars_by_ids", (UUID(int=11),)) in repository.calls
    assert ("history", 10) not in repository.calls


def test_latest_close_snapshot_scope_selects_one_latest_record_from_captured_set() -> None:
    repository = FakeReadRepository()
    repository.items = (
        _item(100, DataCategory.DAILY_PRICES, "daily_price_bars", UUID(int=11)),
        _item(101, DataCategory.DAILY_PRICES, "daily_price_bars", UUID(int=12)),
    )
    result, _ = _execute(
        "get_latest_close",
        {"security_id": SECURITY_ID, "snapshot_id": SNAPSHOT_ID},
        repository,
    )

    assert result.quality.record_count == 1
    assert result.data[0].id == UUID(int=12)


@pytest.mark.parametrize(
    ("snapshot", "warning"),
    (
        (_snapshot(security_id=OTHER_SECURITY_ID), "SNAPSHOT_SECURITY_MISMATCH"),
        (_snapshot(status="BUILDING"), "SNAPSHOT_NOT_TERMINAL"),
        (_snapshot(status="FAILED"), "SNAPSHOT_FAILED"),
    ),
)
def test_snapshot_security_mismatch_and_unreadable_states_fail_closed(
    snapshot: DataSnapshotRecord, warning: str
) -> None:
    repository = FakeReadRepository()
    repository.snapshot_record = snapshot

    result, _ = _execute(
        "get_daily_price_history",
        {"security_id": SECURITY_ID, "snapshot_id": SNAPSHOT_ID, "limit": 10},
        repository,
    )

    assert result.status == ("FAIL" if snapshot.status == "FAILED" else "BLOCKED")
    assert result.data == ()
    assert warning in result.warnings


@pytest.mark.parametrize(
    ("name", "category"),
    (
        ("get_daily_price_history", DataCategory.DAILY_PRICES),
        ("get_corporate_actions", DataCategory.CORPORATE_ACTIONS),
        ("get_reported_financial_facts", DataCategory.FINANCIAL_FACTS),
        ("list_source_documents", DataCategory.FILING_METADATA),
    ),
)
def test_absent_snapshot_category_is_honest_partial_without_fake_records(
    name: str, category: DataCategory
) -> None:
    repository = FakeReadRepository()
    repository.items = tuple(item for item in repository.items if item.category is not category)
    result, _ = _execute(
        name,
        {"security_id": SECURITY_ID, "snapshot_id": SNAPSHOT_ID, "limit": 10},
        repository,
    )

    assert result.status == "PARTIAL"
    assert result.data == ()
    assert result.quality.record_count == 0
    assert f"SNAPSHOT_CATEGORY_ABSENT:{category.value}" in result.warnings
    assert result.provenance.model_dump(mode="json") == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }
    assert "PROVENANCE_UNKNOWN" not in result.warnings


def test_snapshot_document_metadata_requires_the_exact_document_item() -> None:
    repository = FakeReadRepository()
    result, _ = _execute(
        "get_source_document_metadata",
        {
            "document_id": UUID(int=42),
            "security_id": SECURITY_ID,
            "snapshot_id": SNAPSHOT_ID,
        },
        repository,
    )

    assert result.status == "BLOCKED"
    assert result.data == ()
    assert "DOCUMENT_NOT_IN_SNAPSHOT" in result.warnings
    assert result.provenance.model_dump(mode="json") == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }


def test_fixture_provenance_markers_are_exact_and_never_described_as_live() -> None:
    result, _ = _execute(
        "get_reported_financial_facts",
        {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 10},
    )
    serialized = result.model_dump(mode="json")

    assert serialized["provenance"] == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }
    assert "current" not in json.dumps(serialized).lower()
    assert "real-time" not in json.dumps(serialized).lower()


@pytest.mark.parametrize(
    ("provider_ids", "origin", "warning"),
    (
        ((MISSING_PROVIDER_ID,), "UNKNOWN", "PROVENANCE_PROVIDER_UNKNOWN"),
        (
            (FIXTURE_PROVIDER_ID, LIVE_PROVIDER_ID),
            "MIXED",
            "PROVENANCE_MIXED",
        ),
    ),
)
def test_unknown_and_mixed_provenance_are_explicit_and_warning_bearing(
    provider_ids: tuple[UUID, ...], origin: str, warning: str
) -> None:
    repository = FakeReadRepository()
    repository.bars = tuple(
        _bar(
            60 + index,
            close=str(20 + index),
            trading_date=date(2026, 7, 10 - index),
            provider_id=provider_id,
        )
        for index, provider_id in enumerate(provider_ids)
    )
    result, _ = _execute(
        "get_daily_price_history",
        {
            "security_id": SECURITY_ID,
            "research_as_of_time": AS_OF,
            "limit": len(provider_ids),
        },
        repository,
    )

    assert result.provenance.data_origin == origin
    assert warning in result.warnings


def test_history_lower_bound_rebuilds_all_metadata_from_the_returned_subset() -> None:
    repository = FakeReadRepository()
    included = _bar(
        70,
        close="70.00",
        trading_date=date(2026, 7, 10),
        provider_id=FIXTURE_PROVIDER_ID,
        retrieved_at=OLD_RETRIEVED,
    )
    excluded = _bar(
        71,
        close="71.00",
        trading_date=date(2026, 7, 9),
        provider_id=LIVE_PROVIDER_ID,
        retrieved_at=NEW_RETRIEVED,
        published=False,
    )
    repository.bars = (included, excluded)

    result, _ = _execute(
        "get_daily_price_history",
        {
            "security_id": SECURITY_ID,
            "research_as_of_time": AS_OF,
            "date_from": date(2026, 7, 10),
            "local_trading_date": date(2026, 7, 10),
            "limit": 10,
        },
        repository,
    )

    assert result.status == "PASS"
    assert result.data == (result.data[0],)
    assert result.data[0].id == included.id
    assert result.source_record_ids == (included.id,)
    assert result.provider_ids == (FIXTURE_PROVIDER_ID,)
    assert result.retrieved_at == OLD_RETRIEVED
    assert result.warnings == ()
    assert result.quality.record_count == 1
    assert result.provenance.model_dump() == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }


def test_history_input_rejects_lower_bound_after_upper_bound() -> None:
    registry, _repository = _registry()

    with pytest.raises(ToolRegistryError) as captured:
        registry.execute(
            "get_daily_price_history",
            "1.0.0",
            {
                "security_id": SECURITY_ID,
                "research_as_of_time": AS_OF,
                "date_from": date(2026, 7, 11),
                "local_trading_date": date(2026, 7, 10),
                "limit": 10,
            },
        )

    assert captured.value.code is ToolErrorCode.INVALID_INPUT
    assert str(captured.value) == "Tool input was invalid"


def test_decimal_values_are_json_strings_and_raw_financial_semantics_are_preserved() -> None:
    result, _ = _execute(
        "get_reported_financial_facts",
        {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 10},
    )
    dumped = json.loads(result.model_dump_json())
    fact = dumped["data"][0]

    assert fact["value"] == "1234567890.123456789012"
    assert fact["provider_concept"] == "us-gaap:Revenue"
    assert fact["reported_label"] == "Revenue"
    forbidden = {"metric_key", "normalized_value", "ttm", "valuation", "growth", "margin"}
    assert forbidden.isdisjoint(fact)


def test_stable_lineage_retrieval_warnings_and_quality_metadata_are_present() -> None:
    result, _ = _execute(
        "get_corporate_actions",
        {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 10},
    )

    assert result.source_record_ids == (UUID(int=21),)
    assert result.provider_ids == (FIXTURE_PROVIDER_ID,)
    assert result.retrieved_at == OLD_RETRIEVED
    assert result.quality.status == result.status
    assert result.quality.record_count == 1
    assert not hasattr(result.quality, "confidence")


@pytest.mark.parametrize(
    ("name", "attribute"),
    (
        ("get_corporate_actions", "actions"),
        ("get_reported_financial_facts", "facts"),
        ("list_source_documents", "documents"),
    ),
)
def test_empty_evidence_is_partial_and_never_zero_filled_or_invented(
    name: str, attribute: str
) -> None:
    repository = FakeReadRepository()
    setattr(repository, attribute, ())
    result, _ = _execute(
        name,
        {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 10},
        repository,
    )

    assert result.status == "PARTIAL"
    assert result.data == ()
    assert result.quality.record_count == 0


def test_public_snapshot_item_tool_obeys_limit_and_never_uses_builder_replay_port() -> None:
    result, repository = _execute(
        "list_snapshot_items",
        {"snapshot_id": SNAPSHOT_ID, "limit": 2},
    )

    assert result.quality.record_count == 2
    assert ("snapshot_items", 2) in repository.calls


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        ("COMPLETE", "PASS"),
        ("PARTIAL", "PARTIAL"),
        ("FAILED", "FAIL"),
        ("BUILDING", "BLOCKED"),
        ("SUPERSEDED", "BLOCKED"),
    ),
)
def test_snapshot_tool_maps_persisted_states_safely(status: str, expected: str) -> None:
    repository = FakeReadRepository()
    repository.snapshot_record = _snapshot(status=status)
    result, _ = _execute("get_data_snapshot", {"snapshot_id": SNAPSHOT_ID}, repository)

    assert result.status == expected
    assert result.quality.record_count == 1


def test_repository_exceptions_return_fixed_safe_fail_envelopes() -> None:
    repository = FakeReadRepository()
    repository.fail_reads = True
    result, _ = _execute(
        "get_daily_price_history",
        {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 10},
        repository,
    )
    serialized = result.model_dump_json()

    assert result.status == "FAIL"
    assert result.data == ()
    assert "DATA_ACCESS_QUERY_FAILED" in result.warnings
    assert "PROVENANCE_UNKNOWN" in result.warnings
    assert "SECRET_SENTINEL" not in serialized
    assert "RuntimeError" not in serialized


def test_provenance_repository_exception_fails_closed_without_returning_evidence() -> None:
    repository = FakeReadRepository()
    repository.fail_provider_provenance = True
    result, _ = _execute(
        "get_daily_price_history",
        {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 2},
        repository,
    )

    assert result.status == "FAIL"
    assert result.data == ()
    assert "DATA_ACCESS_QUERY_FAILED" in result.warnings
    assert "SECRET_SENTINEL" not in result.model_dump_json()


def test_snapshot_aggregate_repository_exception_fails_snapshot_metadata_closed() -> None:
    repository = FakeReadRepository()
    repository.fail_snapshot_aggregate = True
    result, _ = _execute(
        "get_data_snapshot",
        {"snapshot_id": SNAPSHOT_ID},
        repository,
    )

    assert result.status == "FAIL"
    assert result.data == ()
    assert "DATA_ACCESS_QUERY_FAILED" in result.warnings
    assert "SECRET_SENTINEL" not in result.model_dump_json()


def test_large_snapshot_uses_whole_aggregate_for_mixed_provenance_and_latest_time() -> None:
    repository = FakeReadRepository()
    later = AS_OF - timedelta(minutes=5)
    repository.aggregate_record = SnapshotEvidenceAggregateRecord(
        snapshot_id=SNAPSHOT_ID,
        provider_ids=(FIXTURE_PROVIDER_ID, LIVE_PROVIDER_ID),
        latest_retrieved_at=later,
        item_count=121,
    )
    result, _ = _execute("get_data_snapshot", {"snapshot_id": SNAPSHOT_ID}, repository)

    assert result.provenance.data_origin == "MIXED"
    assert result.provenance.access_mode == "MIXED"
    assert result.provenance.live_status == "MIXED"
    assert result.retrieved_at == later
    assert result.provider_ids == (FIXTURE_PROVIDER_ID, LIVE_PROVIDER_ID)
    assert ("snapshot_evidence_aggregate", SNAPSHOT_ID) in repository.calls
    assert not any(call[0] == "snapshot_items" for call in repository.calls)


def test_large_fixture_only_snapshot_stays_offline_and_not_live() -> None:
    repository = FakeReadRepository()
    repository.aggregate_record = SnapshotEvidenceAggregateRecord(
        snapshot_id=SNAPSHOT_ID,
        provider_ids=(FIXTURE_PROVIDER_ID,),
        latest_retrieved_at=AS_OF - timedelta(minutes=10),
        item_count=121,
    )
    result, _ = _execute("get_data_snapshot", {"snapshot_id": SNAPSHOT_ID}, repository)

    assert result.provenance.model_dump(mode="json") == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }


def _distinct_provider_ids(count: int) -> tuple[UUID, ...]:
    return tuple(sorted((UUID(int=10_000 + index) for index in range(count)), key=str))


@pytest.mark.parametrize(
    ("provider_count", "expected_chunk_sizes"),
    ((101, (100, 1)), (396, (100, 100, 100, 96))),
)
def test_large_distinct_fixture_provider_sets_are_queried_in_bounded_chunks(
    provider_count: int,
    expected_chunk_sizes: tuple[int, ...],
) -> None:
    repository = FakeReadRepository()
    provider_ids = _distinct_provider_ids(provider_count)
    repository.providers = {
        provider_id: ProviderProvenanceRecord(
            id=provider_id,
            code=f"FIXTURE_{index:03d}",
            provider_type="FIXTURE",
            status="EXPERIMENTAL",
            terms_status="NEEDS_REVIEW",
        )
        for index, provider_id in enumerate(provider_ids)
    }
    repository.aggregate_record = SnapshotEvidenceAggregateRecord(
        snapshot_id=SNAPSHOT_ID,
        provider_ids=provider_ids,
        latest_retrieved_at=NEW_RETRIEVED,
        item_count=provider_count,
    )

    result, _ = _execute("get_data_snapshot", {"snapshot_id": SNAPSHOT_ID}, repository)

    provenance_calls = tuple(
        cast(tuple[UUID, ...], value)
        for name, value in repository.calls
        if name == "provider_provenance"
    )
    assert tuple(len(value) for value in provenance_calls) == expected_chunk_sizes
    assert tuple(provider_id for chunk in provenance_calls for provider_id in chunk) == provider_ids
    assert result.status == "PASS"
    assert result.provenance.model_dump(mode="json") == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }


def test_provider_provenance_chunks_merge_stably_to_mixed() -> None:
    repository = FakeReadRepository()
    provider_ids = _distinct_provider_ids(101)
    repository.providers = {
        provider_id: ProviderProvenanceRecord(
            id=provider_id,
            code=f"PROVIDER_{index:03d}",
            provider_type="MARKET_DATA" if index == 100 else "FIXTURE",
            status="APPROVED" if index == 100 else "EXPERIMENTAL",
            terms_status="VERIFIED" if index == 100 else "NEEDS_REVIEW",
        )
        for index, provider_id in enumerate(provider_ids)
    }
    repository.aggregate_record = SnapshotEvidenceAggregateRecord(
        snapshot_id=SNAPSHOT_ID,
        provider_ids=provider_ids,
        latest_retrieved_at=NEW_RETRIEVED,
        item_count=101,
    )

    result, _ = _execute("get_data_snapshot", {"snapshot_id": SNAPSHOT_ID}, repository)

    assert result.status == "PASS"
    assert result.provider_ids == provider_ids
    assert result.provenance.model_dump(mode="json") == {
        "data_origin": "MIXED",
        "access_mode": "MIXED",
        "live_status": "MIXED",
    }
    assert "PROVENANCE_MIXED" in result.warnings


def test_missing_provider_in_later_provenance_chunk_still_fails_closed() -> None:
    repository = FakeReadRepository()
    provider_ids = _distinct_provider_ids(101)
    repository.providers = {
        provider_id: ProviderProvenanceRecord(
            id=provider_id,
            code=f"FIXTURE_{index:03d}",
            provider_type="FIXTURE",
            status="EXPERIMENTAL",
            terms_status="NEEDS_REVIEW",
        )
        for index, provider_id in enumerate(provider_ids[:-1])
    }
    repository.aggregate_record = SnapshotEvidenceAggregateRecord(
        snapshot_id=SNAPSHOT_ID,
        provider_ids=provider_ids,
        latest_retrieved_at=NEW_RETRIEVED,
        item_count=101,
    )

    result, _ = _execute("get_data_snapshot", {"snapshot_id": SNAPSHOT_ID}, repository)

    assert result.status == "FAIL"
    assert result.data == ()
    assert result.provider_ids == ()
    assert result.provenance.data_origin == "UNKNOWN"
    assert "PROVENANCE_PROVIDER_UNKNOWN" in result.warnings


def test_unavailable_whole_snapshot_aggregate_fails_closed_to_unknown_provenance() -> None:
    repository = FakeReadRepository()
    repository.aggregate_record = None
    result, _ = _execute("get_data_snapshot", {"snapshot_id": SNAPSHOT_ID}, repository)

    assert result.status == "FAIL"
    assert result.provenance.data_origin == "UNKNOWN"
    assert result.data == ()
    assert "SNAPSHOT_AGGREGATION_UNAVAILABLE" in result.warnings


def test_inconsistent_whole_snapshot_count_fails_closed_to_unknown_provenance() -> None:
    repository = FakeReadRepository()
    repository.aggregate_record = SnapshotEvidenceAggregateRecord.model_construct(
        snapshot_id=SNAPSHOT_ID,
        provider_ids=(FIXTURE_PROVIDER_ID,),
        latest_retrieved_at=OLD_RETRIEVED,
        item_count=0,
    )
    result, _ = _execute("get_data_snapshot", {"snapshot_id": SNAPSHOT_ID}, repository)

    assert result.status == "FAIL"
    assert result.provenance.data_origin == "UNKNOWN"
    assert result.data == ()
    assert "SNAPSHOT_AGGREGATION_INCONSISTENT" in result.warnings


def test_tool_outputs_exclude_raw_storage_path_secret_sql_header_and_confidence_fields() -> None:
    registry, _repository = _registry()
    outputs = (
        registry.execute(
            "get_daily_price_history",
            "1.0.0",
            {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 2},
        ),
        registry.execute(
            "get_reported_financial_facts",
            "1.0.0",
            {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 2},
        ),
        registry.execute(
            "list_source_documents",
            "1.0.0",
            {"security_id": SECURITY_ID, "research_as_of_time": AS_OF, "limit": 2},
        ),
        registry.execute(
            "list_snapshot_items",
            "1.0.0",
            {"snapshot_id": SNAPSHOT_ID, "limit": 2},
        ),
    )
    forbidden = {
        "confidence",
        "connection_string",
        "headers",
        "inline_json",
        "raw_payload",
        "request_headers",
        "secret",
        "sql",
        "stack_trace",
        "storage_uri",
        "token",
    }
    for output in outputs:
        keys = _all_keys(cast(dict[str, Any], output.model_dump(mode="json")))
        assert forbidden.isdisjoint(keys)
        assert "checksum_input" not in keys
        assert "source_payload_id" not in keys


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {nested for item in value.values() for nested in _all_keys(item)}
    if isinstance(value, list):
        return {nested for item in value for nested in _all_keys(item)}
    return set()
