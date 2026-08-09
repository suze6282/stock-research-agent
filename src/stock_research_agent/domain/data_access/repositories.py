"""Model-independent persistence ports for Stage 4 raw data access."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from stock_research_agent.domain.data_access.enums import DataCategory
from stock_research_agent.domain.data_access.schemas import (
    CorporateActionRecord,
    CorporateActionWrite,
    DailyPriceBarRecord,
    DailyPriceBarWrite,
    DataProviderRecord,
    DataProviderWrite,
    DataSnapshotRecord,
    DataSnapshotUpdate,
    DataSnapshotWrite,
    IngestionRunRecord,
    IngestionRunUpdate,
    IngestionRunWrite,
    ProviderFinancialFactRecord,
    ProviderFinancialFactWrite,
    ProviderInstrument,
    ProviderInstrumentMappingRecord,
    ProviderInstrumentMappingWrite,
    ProviderProvenanceRecord,
    ProviderRequestLogRecord,
    ProviderRequestLogWrite,
    RawPayloadMetadataRecord,
    RawPayloadRecord,
    RawPayloadWrite,
    SnapshotEvidenceAggregateRecord,
    SnapshotItemRecord,
    SnapshotItemWrite,
    SourceDocumentRecord,
    SourceDocumentWrite,
)


class StoredDataValidationError(RuntimeError):
    """Stored data was rejected without exposing its unsafe value or validation details."""


class ProviderCatalogRepository(Protocol):
    def list_providers(self, limit: int) -> Sequence[DataProviderRecord]: ...

    def get_provider(self, code: str) -> DataProviderRecord | None: ...


class ProviderMappingRepository(Protocol):
    def get_active_mapping(
        self,
        security_id: UUID,
        provider_code: str,
        as_of: date,
    ) -> ProviderInstrument | None: ...


class ProviderMappingListRepository(Protocol):
    """Narrow Stage 4 CLI read port for bounded mappings by persisted security."""

    def list_provider_mappings(
        self,
        security_id: UUID,
        limit: int,
    ) -> Sequence[ProviderInstrumentMappingRecord]: ...


class DataAccessReadRepository(
    ProviderCatalogRepository,
    ProviderMappingRepository,
    ProviderMappingListRepository,
    Protocol,
):
    def list_provider_provenance(
        self, provider_ids: tuple[UUID, ...]
    ) -> Sequence[ProviderProvenanceRecord]: ...

    def get_ingestion_run(self, run_id: UUID) -> IngestionRunRecord | None: ...

    def get_ingestion_run_by_idempotency_key(self, key: str) -> IngestionRunRecord | None: ...

    def list_request_lineage(
        self, run_id: UUID, limit: int
    ) -> Sequence[ProviderRequestLogRecord]: ...

    def list_raw_payload_lineage(
        self, run_id: UUID, limit: int
    ) -> Sequence[RawPayloadMetadataRecord]: ...

    def get_latest_close(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        local_trading_date: date | None,
    ) -> DailyPriceBarRecord | None: ...

    def list_daily_history(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        local_trading_date: date | None,
        limit: int,
        provider_id: UUID | None = None,
    ) -> Sequence[DailyPriceBarRecord]: ...

    def list_daily_prices_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> Sequence[DailyPriceBarRecord]: ...

    def list_corporate_actions(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> Sequence[CorporateActionRecord]: ...

    def list_corporate_actions_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> Sequence[CorporateActionRecord]: ...

    def list_financial_facts(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> Sequence[ProviderFinancialFactRecord]: ...

    def list_financial_facts_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> Sequence[ProviderFinancialFactRecord]: ...

    def list_source_documents(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> Sequence[SourceDocumentRecord]: ...

    def get_source_document_metadata(
        self,
        document_id: UUID,
        security_id: UUID,
        research_as_of_time: datetime,
    ) -> SourceDocumentRecord | None: ...

    def list_source_documents_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> Sequence[SourceDocumentRecord]: ...

    def get_snapshot(self, snapshot_id: UUID) -> DataSnapshotRecord | None: ...

    def get_latest_eligible_snapshot(
        self, security_id: UUID, research_as_of_time: datetime
    ) -> DataSnapshotRecord | None: ...

    def get_latest_snapshot_at_as_of(
        self, security_id: UUID, research_as_of_time: datetime
    ) -> DataSnapshotRecord | None: ...

    def list_snapshot_items(
        self, snapshot_id: UUID, limit: int
    ) -> Sequence[SnapshotItemRecord]: ...

    def list_snapshot_items_by_category(
        self,
        snapshot_id: UUID,
        category: DataCategory,
        limit: int,
    ) -> Sequence[SnapshotItemRecord]: ...

    def get_snapshot_evidence_aggregate(
        self, snapshot_id: UUID
    ) -> SnapshotEvidenceAggregateRecord | None: ...

    def list_snapshot_items_for_replay(self, snapshot_id: UUID) -> Sequence[SnapshotItemRecord]: ...


class DataAccessWriteRepository(Protocol):
    def add_provider(self, value: DataProviderWrite) -> DataProviderRecord: ...

    def add_provider_mapping(
        self, value: ProviderInstrumentMappingWrite
    ) -> ProviderInstrumentMappingRecord: ...

    def create_ingestion_run(self, value: IngestionRunWrite) -> IngestionRunRecord: ...

    def get_or_create_ingestion_run(
        self, value: IngestionRunWrite
    ) -> tuple[IngestionRunRecord, bool]: ...

    def ingestion_attempt(self) -> AbstractContextManager[None]: ...

    def update_ingestion_run(
        self, run_id: UUID, value: IngestionRunUpdate
    ) -> IngestionRunRecord: ...

    def add_request_log(self, value: ProviderRequestLogWrite) -> ProviderRequestLogRecord: ...

    def add_raw_payload(self, value: RawPayloadWrite) -> RawPayloadRecord: ...

    def add_daily_price_bar(self, value: DailyPriceBarWrite) -> DailyPriceBarRecord: ...

    def add_corporate_action(self, value: CorporateActionWrite) -> CorporateActionRecord: ...

    def add_financial_fact(
        self, value: ProviderFinancialFactWrite
    ) -> ProviderFinancialFactRecord: ...

    def add_source_document(self, value: SourceDocumentWrite) -> SourceDocumentRecord: ...

    def add_snapshot(self, value: DataSnapshotWrite) -> DataSnapshotRecord: ...

    def get_or_create_snapshot(
        self, value: DataSnapshotWrite
    ) -> tuple[DataSnapshotRecord, bool]: ...

    def snapshot_attempt(self) -> AbstractContextManager[None]: ...

    def update_snapshot(
        self, snapshot_id: UUID, value: DataSnapshotUpdate
    ) -> DataSnapshotRecord: ...

    def add_snapshot_item(self, value: SnapshotItemWrite) -> SnapshotItemRecord: ...


class DataAccessRepository(DataAccessReadRepository, DataAccessWriteRepository, Protocol):
    """Composite port for transaction-owning internal services."""
