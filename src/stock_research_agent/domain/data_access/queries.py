"""Pure, read-only query service shared by future API, CLI, and Tool layers."""

from __future__ import annotations

from datetime import date, datetime
from typing import TypeVar
from uuid import UUID

from stock_research_agent.domain.data_access.enums import DataCategory, QualityStatus
from stock_research_agent.domain.data_access.repositories import DataAccessReadRepository
from stock_research_agent.domain.data_access.schemas import (
    CorporateActionRecord,
    DailyPriceBarRecord,
    DataProviderRecord,
    DataQueryResult,
    DataSnapshotRecord,
    ProviderFinancialFactRecord,
    ProviderProvenanceRecord,
    SnapshotEvidenceAggregateRecord,
    SnapshotItemRecord,
    SourceDocumentRecord,
)

ResultT = TypeVar("ResultT")


class DataAccessQueryService:
    """Apply stable empty/partial semantics without performing I/O beyond the read port."""

    def __init__(self, repository: DataAccessReadRepository) -> None:
        self._repository = repository

    def provider_catalog(self, limit: int = 100) -> DataQueryResult[DataProviderRecord]:
        validated = self._validated_limit(limit)
        records = tuple(self._repository.list_providers(validated))
        return self._result(records, empty_warning="NO_PROVIDERS_CONFIGURED", empty_blocked=True)

    def provider_provenance(
        self, provider_ids: tuple[UUID, ...]
    ) -> DataQueryResult[ProviderProvenanceRecord]:
        validated = self._validated_ids(provider_ids)
        records = tuple(self._repository.list_provider_provenance(validated))
        return self._result(records, empty_warning="NO_PROVIDER_PROVENANCE")

    def latest_close(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        local_trading_date: date | None,
    ) -> DataQueryResult[DailyPriceBarRecord]:
        record = self._repository.get_latest_close(
            security_id,
            research_as_of_time,
            local_trading_date,
        )
        records = () if record is None else (record,)
        return self._result(records, empty_warning="NO_DAILY_PRICE_DATA")

    def daily_history(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        local_trading_date: date | None,
        limit: int,
    ) -> DataQueryResult[DailyPriceBarRecord]:
        validated = self._validated_limit(limit)
        records = tuple(
            self._repository.list_daily_history(
                security_id,
                research_as_of_time,
                local_trading_date,
                validated,
            )
        )
        return self._result(records, empty_warning="NO_DAILY_PRICE_DATA")

    def daily_prices_by_ids(
        self,
        security_id: UUID,
        source_ids: tuple[UUID, ...],
    ) -> DataQueryResult[DailyPriceBarRecord]:
        records = tuple(
            self._repository.list_daily_prices_by_ids(
                security_id,
                self._validated_ids(source_ids),
            )
        )
        return self._result(records, empty_warning="NO_SNAPSHOT_DAILY_PRICE_RECORDS")

    def corporate_actions(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
    ) -> DataQueryResult[CorporateActionRecord]:
        records = tuple(
            self._repository.list_corporate_actions(
                security_id, research_as_of_time, self._validated_limit(limit)
            )
        )
        return self._result(records, empty_warning="NO_CORPORATE_ACTION_DATA")

    def corporate_actions_by_ids(
        self,
        security_id: UUID,
        source_ids: tuple[UUID, ...],
    ) -> DataQueryResult[CorporateActionRecord]:
        records = tuple(
            self._repository.list_corporate_actions_by_ids(
                security_id,
                self._validated_ids(source_ids),
            )
        )
        return self._result(records, empty_warning="NO_SNAPSHOT_CORPORATE_ACTION_RECORDS")

    def reported_financial_facts(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
    ) -> DataQueryResult[ProviderFinancialFactRecord]:
        records = tuple(
            self._repository.list_financial_facts(
                security_id, research_as_of_time, self._validated_limit(limit)
            )
        )
        return self._result(records, empty_warning="NO_REPORTED_FINANCIAL_FACTS")

    def financial_facts_by_ids(
        self,
        security_id: UUID,
        source_ids: tuple[UUID, ...],
    ) -> DataQueryResult[ProviderFinancialFactRecord]:
        records = tuple(
            self._repository.list_financial_facts_by_ids(
                security_id,
                self._validated_ids(source_ids),
            )
        )
        return self._result(records, empty_warning="NO_SNAPSHOT_FINANCIAL_FACT_RECORDS")

    def source_documents(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
    ) -> DataQueryResult[SourceDocumentRecord]:
        records = tuple(
            self._repository.list_source_documents(
                security_id, research_as_of_time, self._validated_limit(limit)
            )
        )
        return self._result(records, empty_warning="NO_SOURCE_DOCUMENTS")

    def source_document_metadata(
        self,
        document_id: UUID,
        security_id: UUID,
        research_as_of_time: datetime,
    ) -> DataQueryResult[SourceDocumentRecord]:
        record = self._repository.get_source_document_metadata(
            document_id,
            security_id,
            research_as_of_time,
        )
        records = () if record is None else (record,)
        return self._result(records, empty_warning="SOURCE_DOCUMENT_NOT_FOUND")

    def source_documents_by_ids(
        self,
        security_id: UUID,
        source_ids: tuple[UUID, ...],
    ) -> DataQueryResult[SourceDocumentRecord]:
        records = tuple(
            self._repository.list_source_documents_by_ids(
                security_id,
                self._validated_ids(source_ids),
            )
        )
        return self._result(records, empty_warning="NO_SNAPSHOT_SOURCE_DOCUMENT_RECORDS")

    def snapshot(self, snapshot_id: UUID) -> DataQueryResult[DataSnapshotRecord]:
        record = self._repository.get_snapshot(snapshot_id)
        return self._snapshot_result(record)

    def latest_snapshot(
        self, security_id: UUID, research_as_of_time: datetime
    ) -> DataQueryResult[DataSnapshotRecord]:
        record = self._repository.get_latest_eligible_snapshot(security_id, research_as_of_time)
        return self._snapshot_result(record)

    def snapshot_items(self, snapshot_id: UUID, limit: int) -> DataQueryResult[SnapshotItemRecord]:
        records = tuple(
            self._repository.list_snapshot_items(snapshot_id, self._validated_limit(limit))
        )
        return self._result(records, empty_warning="NO_SNAPSHOT_ITEMS")

    def snapshot_items_by_category(
        self,
        snapshot_id: UUID,
        category: DataCategory,
        limit: int,
    ) -> DataQueryResult[SnapshotItemRecord]:
        records = tuple(
            self._repository.list_snapshot_items_by_category(
                snapshot_id,
                category,
                self._validated_limit(limit),
            )
        )
        return self._result(records, empty_warning=f"NO_SNAPSHOT_ITEMS:{category.value}")

    def snapshot_evidence_aggregate(
        self, snapshot_id: UUID
    ) -> DataQueryResult[SnapshotEvidenceAggregateRecord]:
        record = self._repository.get_snapshot_evidence_aggregate(snapshot_id)
        if record is None:
            return DataQueryResult(
                status=QualityStatus.FAIL,
                records=(),
                warnings=("SNAPSHOT_AGGREGATION_UNAVAILABLE",),
            )
        return DataQueryResult(status=QualityStatus.PASS, records=(record,), warnings=())

    @staticmethod
    def _result(
        records: tuple[ResultT, ...],
        *,
        empty_warning: str,
        empty_blocked: bool = False,
    ) -> DataQueryResult[ResultT]:
        if not records:
            status = QualityStatus.BLOCKED if empty_blocked else QualityStatus.PARTIAL
            return DataQueryResult(status=status, records=(), warnings=(empty_warning,))
        publication_unknown = any(
            (hasattr(record, "source_published_at") and record.source_published_at is None)
            or (hasattr(record, "published_at") and record.published_at is None)
            for record in records
        )
        warnings = ("SOURCE_PUBLISHED_AT_UNKNOWN",) if publication_unknown else ()
        status = QualityStatus.PARTIAL if warnings else QualityStatus.PASS
        return DataQueryResult(status=status, records=records, warnings=warnings)

    @staticmethod
    def _validated_limit(limit: int) -> int:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return limit

    @staticmethod
    def _validated_ids(values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if not values or len(values) > 100 or len(set(values)) != len(values):
            raise ValueError("source IDs must be unique and bounded between 1 and 100")
        return values

    @staticmethod
    def _snapshot_result(
        record: DataSnapshotRecord | None,
    ) -> DataQueryResult[DataSnapshotRecord]:
        if record is None:
            return DataQueryResult(
                status=QualityStatus.BLOCKED,
                records=(),
                warnings=("SNAPSHOT_NOT_FOUND",),
            )
        status_mapping = {
            "COMPLETE": (QualityStatus.PASS, ()),
            "PARTIAL": (QualityStatus.PARTIAL, ("SNAPSHOT_PARTIAL",)),
            "FAILED": (QualityStatus.FAIL, ("SNAPSHOT_FAILED",)),
            "BUILDING": (QualityStatus.PARTIAL, ("SNAPSHOT_BUILDING",)),
            "SUPERSEDED": (QualityStatus.PARTIAL, ("SNAPSHOT_SUPERSEDED",)),
        }
        query_status, warnings = status_mapping[record.status]
        return DataQueryResult(status=query_status, records=(record,), warnings=warnings)
