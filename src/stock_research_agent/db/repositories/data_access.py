"""SQLAlchemy implementation of the Stage 4 data-access persistence ports."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from typing import TypeVar, cast
from uuid import UUID

from pydantic import JsonValue, ValidationError
from sqlalchemy import Select, func, null, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from stock_research_agent.db.models import (
    CorporateAction,
    DailyPriceBar,
    DataProvider,
    DataSnapshot,
    IngestionRun,
    ProviderFinancialFact,
    ProviderInstrumentMapping,
    ProviderRequestLog,
    RawPayload,
    SnapshotItem,
    SourceDocument,
)
from stock_research_agent.domain.data_access.enums import DataCategory
from stock_research_agent.domain.data_access.repositories import StoredDataValidationError
from stock_research_agent.domain.data_access.schemas import (
    CorporateActionRecord,
    CorporateActionWrite,
    DailyPriceBarRecord,
    DailyPriceBarWrite,
    DataAccessModel,
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

EntityT = TypeVar("EntityT", bound=DeclarativeBase)
RecordT = TypeVar("RecordT", bound=DataAccessModel)
_SNAPSHOT_REPLAY_ITEM_LIMIT = 396
_SNAPSHOT_AGGREGATION_ITEM_LIMIT = 396


class SqlAlchemyDataAccessRepository:
    """Operate on a caller-owned Session without owning its transaction or lifecycle."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_provider(self, value: DataProviderWrite) -> DataProviderRecord:
        entity = DataProvider(**value.model_dump(mode="python"))
        self._session.add(entity)
        self._session.flush()
        return DataProviderRecord.model_validate(entity)

    def add_provider_mapping(
        self, value: ProviderInstrumentMappingWrite
    ) -> ProviderInstrumentMappingRecord:
        values = value.model_dump(mode="python")
        metadata = values.pop("metadata")
        entity = ProviderInstrumentMapping(**values, mapping_metadata=metadata)
        self._session.add(entity)
        self._session.flush()
        return self._mapping_record(entity)

    def create_ingestion_run(self, value: IngestionRunWrite) -> IngestionRunRecord:
        entity = IngestionRun(
            **value.model_dump(mode="python"),
            status="QUEUED",
            request_count=0,
            records_received=0,
            records_stored=0,
            warning_count=0,
        )
        self._session.add(entity)
        self._session.flush()
        return IngestionRunRecord.model_validate(entity)

    def get_or_create_ingestion_run(
        self, value: IngestionRunWrite
    ) -> tuple[IngestionRunRecord, bool]:
        existing = self.get_ingestion_run_by_idempotency_key(value.idempotency_key)
        if existing is not None:
            return existing, False
        try:
            with self._session.begin_nested():
                created = self.create_ingestion_run(value)
            return created, True
        except IntegrityError:
            existing = self.get_ingestion_run_by_idempotency_key(value.idempotency_key)
            if existing is None:
                raise
            return existing, False

    @contextmanager
    def ingestion_attempt(self) -> Iterator[None]:
        with self._session.begin_nested():
            yield

    def update_ingestion_run(self, run_id: UUID, value: IngestionRunUpdate) -> IngestionRunRecord:
        entity = self._session.get(IngestionRun, run_id)
        if entity is None:
            raise LookupError(f"ingestion run {run_id} was not found")
        updates = value.model_dump(mode="python", exclude_unset=True)
        status = cast(str, updates.get("status", entity.status))
        started_at = cast(datetime | None, updates.get("started_at", entity.started_at))
        completed_at = cast(datetime | None, updates.get("completed_at", entity.completed_at))
        self._validate_ingestion_state(
            status=status,
            requested_at=entity.requested_at,
            started_at=started_at,
            completed_at=completed_at,
        )
        for field_name, field_value in updates.items():
            setattr(entity, field_name, field_value)
        self._session.flush()
        return IngestionRunRecord.model_validate(entity)

    def add_request_log(self, value: ProviderRequestLogWrite) -> ProviderRequestLogRecord:
        entity = ProviderRequestLog(**value.model_dump(mode="python"))
        self._session.add(entity)
        self._session.flush()
        return ProviderRequestLogRecord.model_validate(entity)

    def add_raw_payload(self, value: RawPayloadWrite) -> RawPayloadRecord:
        values = value.model_dump(
            mode="python",
            exclude={"manual_evidence_import_request_id"},
        )
        if value.storage_uri is not None:
            # PostgreSQL JSONB encodes Python None as JSON null. The persistence
            # contract requires SQL NULL for the non-selected storage branch.
            values["inline_json"] = null()
        entity = RawPayload(**values)
        self._session.add(entity)
        self._session.flush()
        return RawPayloadRecord.model_validate(entity)

    def add_daily_price_bar(self, value: DailyPriceBarWrite) -> DailyPriceBarRecord:
        entity = DailyPriceBar(**value.model_dump(mode="python"))
        self._session.add(entity)
        self._session.flush()
        return DailyPriceBarRecord.model_validate(entity)

    def add_corporate_action(self, value: CorporateActionWrite) -> CorporateActionRecord:
        entity = CorporateAction(**value.model_dump(mode="python"))
        self._session.add(entity)
        self._session.flush()
        return CorporateActionRecord.model_validate(entity)

    def add_financial_fact(self, value: ProviderFinancialFactWrite) -> ProviderFinancialFactRecord:
        entity = ProviderFinancialFact(**value.model_dump(mode="python"))
        self._session.add(entity)
        self._session.flush()
        return ProviderFinancialFactRecord.model_validate(entity)

    def add_source_document(self, value: SourceDocumentWrite) -> SourceDocumentRecord:
        entity = SourceDocument(**value.model_dump(mode="python"))
        self._session.add(entity)
        self._session.flush()
        return SourceDocumentRecord.model_validate(entity)

    def add_snapshot(self, value: DataSnapshotWrite) -> DataSnapshotRecord:
        entity = DataSnapshot(**value.model_dump(mode="python"))
        self._session.add(entity)
        self._session.flush()
        return DataSnapshotRecord.model_validate(entity)

    def get_or_create_snapshot(self, value: DataSnapshotWrite) -> tuple[DataSnapshotRecord, bool]:
        statement = (
            select(DataSnapshot)
            .where(
                DataSnapshot.security_id == value.security_id,
                DataSnapshot.research_as_of_time == value.research_as_of_time,
                DataSnapshot.snapshot_version == value.snapshot_version,
            )
            .with_for_update()
        )
        with self._session.no_autoflush:
            existing = self._session.scalar(statement)
        if existing is not None:
            return self._safe_record(DataSnapshotRecord, existing), False
        try:
            with self._session.begin_nested():
                created = self.add_snapshot(value)
            return created, True
        except IntegrityError:
            with self._session.no_autoflush:
                existing = self._session.scalar(statement)
            if existing is None:
                raise
            return self._safe_record(DataSnapshotRecord, existing), False

    @contextmanager
    def snapshot_attempt(self) -> Iterator[None]:
        with self._session.begin_nested():
            yield

    def update_snapshot(self, snapshot_id: UUID, value: DataSnapshotUpdate) -> DataSnapshotRecord:
        entity = self._session.scalar(
            select(DataSnapshot).where(DataSnapshot.id == snapshot_id).with_for_update()
        )
        if entity is None:
            raise LookupError("snapshot was not found")
        if entity.status != "BUILDING":
            raise ValueError("terminal snapshot is immutable")
        for field_name, field_value in value.model_dump(mode="python").items():
            setattr(entity, field_name, field_value)
        self._session.flush()
        return self._safe_record(DataSnapshotRecord, entity)

    def add_snapshot_item(self, value: SnapshotItemWrite) -> SnapshotItemRecord:
        entity = SnapshotItem(**value.model_dump(mode="python"))
        self._session.add(entity)
        self._session.flush()
        return SnapshotItemRecord.model_validate(entity)

    def list_providers(self, limit: int) -> tuple[DataProviderRecord, ...]:
        statement = select(DataProvider).order_by(DataProvider.code, DataProvider.id)
        return self._load(statement, DataProviderRecord, limit)

    def list_provider_provenance(
        self, provider_ids: tuple[UUID, ...]
    ) -> tuple[ProviderProvenanceRecord, ...]:
        validated = self._validated_ids(provider_ids)
        statement = (
            select(
                DataProvider.id,
                DataProvider.code,
                DataProvider.provider_type,
                DataProvider.status,
                DataProvider.terms_status,
            )
            .where(DataProvider.id.in_(validated))
            .limit(len(validated))
        )
        with self._session.no_autoflush:
            rows = self._session.execute(statement).mappings().all()
        records = {
            row["id"]: self._safe_record(ProviderProvenanceRecord, dict(row)) for row in rows
        }
        return tuple(records[value] for value in validated if value in records)

    def get_provider(self, code: str) -> DataProviderRecord | None:
        with self._session.no_autoflush:
            entity = self._session.scalar(select(DataProvider).where(DataProvider.code == code))
        return None if entity is None else self._safe_record(DataProviderRecord, entity)

    def get_active_mapping(
        self,
        security_id: UUID,
        provider_code: str,
        as_of: date,
    ) -> ProviderInstrument | None:
        statement = (
            select(ProviderInstrumentMapping)
            .join(DataProvider, ProviderInstrumentMapping.provider_id == DataProvider.id)
            .where(
                ProviderInstrumentMapping.security_id == security_id,
                DataProvider.code == provider_code,
                or_(
                    ProviderInstrumentMapping.valid_from.is_(None),
                    ProviderInstrumentMapping.valid_from <= as_of,
                ),
                or_(
                    ProviderInstrumentMapping.valid_to.is_(None),
                    ProviderInstrumentMapping.valid_to >= as_of,
                ),
            )
            .order_by(
                ProviderInstrumentMapping.is_primary.desc(),
                ProviderInstrumentMapping.valid_from.desc().nullslast(),
                ProviderInstrumentMapping.id,
            )
            .limit(1)
        )
        with self._session.no_autoflush:
            entity = self._session.scalar(statement)
        if entity is None:
            return None
        return self._safe_record(
            ProviderInstrument,
            {
                "security_id": entity.security_id,
                "provider_symbol": entity.provider_symbol,
                "provider_exchange_code": entity.provider_exchange_code,
                "provider_instrument_id": entity.provider_instrument_id,
            },
        )

    def list_provider_mappings(
        self,
        security_id: UUID,
        limit: int,
    ) -> tuple[ProviderInstrumentMappingRecord, ...]:
        statement = (
            select(ProviderInstrumentMapping)
            .where(ProviderInstrumentMapping.security_id == security_id)
            .order_by(
                ProviderInstrumentMapping.provider_id,
                ProviderInstrumentMapping.provider_symbol,
                ProviderInstrumentMapping.valid_from.asc().nullsfirst(),
                ProviderInstrumentMapping.id,
            )
        )
        with self._session.no_autoflush:
            entities = self._session.scalars(statement.limit(self._validated_limit(limit))).all()
        return tuple(self._mapping_record(entity) for entity in entities)

    def get_ingestion_run(self, run_id: UUID) -> IngestionRunRecord | None:
        with self._session.no_autoflush:
            entity = self._session.get(IngestionRun, run_id)
        return None if entity is None else self._safe_record(IngestionRunRecord, entity)

    def get_ingestion_run_by_idempotency_key(self, key: str) -> IngestionRunRecord | None:
        with self._session.no_autoflush:
            entity = self._session.scalar(
                select(IngestionRun).where(IngestionRun.idempotency_key == key)
            )
        return None if entity is None else self._safe_record(IngestionRunRecord, entity)

    def list_request_lineage(
        self, run_id: UUID, limit: int
    ) -> tuple[ProviderRequestLogRecord, ...]:
        statement = (
            select(ProviderRequestLog)
            .where(ProviderRequestLog.ingestion_run_id == run_id)
            .order_by(ProviderRequestLog.created_at, ProviderRequestLog.id)
        )
        return self._load(statement, ProviderRequestLogRecord, limit)

    def list_raw_payload_lineage(
        self, run_id: UUID, limit: int
    ) -> tuple[RawPayloadMetadataRecord, ...]:
        statement = (
            select(
                RawPayload.id,
                RawPayload.ingestion_run_id,
                RawPayload.provider_request_log_id,
                RawPayload.provider_id,
                RawPayload.security_id,
                RawPayload.category,
                RawPayload.content_type,
                RawPayload.checksum_algorithm,
                RawPayload.checksum,
                RawPayload.source_published_at,
                RawPayload.retrieved_at,
                RawPayload.provider_version,
                RawPayload.parser_version,
                RawPayload.schema_version,
                RawPayload.byte_size,
                RawPayload.created_at,
            )
            .where(RawPayload.ingestion_run_id == run_id)
            .order_by(RawPayload.created_at, RawPayload.id)
            .limit(self._validated_limit(limit))
        )
        with self._session.no_autoflush:
            rows = self._session.execute(statement).mappings().all()
        return tuple(self._safe_record(RawPayloadMetadataRecord, dict(row)) for row in rows)

    def get_latest_close(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        local_trading_date: date | None,
    ) -> DailyPriceBarRecord | None:
        rows = self.list_daily_history(
            security_id,
            research_as_of_time=research_as_of_time,
            local_trading_date=local_trading_date,
            limit=1,
        )
        return rows[0] if rows else None

    def list_daily_history(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        local_trading_date: date | None,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[DailyPriceBarRecord, ...]:
        statement = select(DailyPriceBar).where(
            DailyPriceBar.security_id == security_id,
            DailyPriceBar.retrieved_at <= research_as_of_time,
            self._published_by(DailyPriceBar.source_published_at, research_as_of_time),
        )
        if local_trading_date is not None:
            statement = statement.where(DailyPriceBar.trading_date <= local_trading_date)
        if provider_id is not None:
            statement = statement.where(DailyPriceBar.provider_id == provider_id)
        statement = statement.order_by(
            DailyPriceBar.trading_date.desc(),
            DailyPriceBar.retrieved_at.desc(),
            DailyPriceBar.id,
        )
        return self._load(statement, DailyPriceBarRecord, limit)

    def list_daily_prices_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> tuple[DailyPriceBarRecord, ...]:
        validated = self._validated_ids(source_ids)
        statement = select(DailyPriceBar).where(
            DailyPriceBar.security_id == security_id,
            DailyPriceBar.id.in_(validated),
        )
        records = self._load(statement, DailyPriceBarRecord, len(validated))
        by_id = {record.id: record for record in records}
        return tuple(by_id[value] for value in validated if value in by_id)

    def list_corporate_actions(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[CorporateActionRecord, ...]:
        statement = (
            select(CorporateAction)
            .where(
                CorporateAction.security_id == security_id,
                CorporateAction.retrieved_at <= research_as_of_time,
                self._published_by(CorporateAction.source_published_at, research_as_of_time),
            )
            .order_by(
                CorporateAction.ex_date.desc().nullslast(),
                CorporateAction.retrieved_at.desc(),
                CorporateAction.id,
            )
        )
        if provider_id is not None:
            statement = statement.where(CorporateAction.provider_id == provider_id)
        return self._load(statement, CorporateActionRecord, limit)

    def list_corporate_actions_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> tuple[CorporateActionRecord, ...]:
        validated = self._validated_ids(source_ids)
        statement = select(CorporateAction).where(
            CorporateAction.security_id == security_id,
            CorporateAction.id.in_(validated),
        )
        records = self._load(statement, CorporateActionRecord, len(validated))
        by_id = {record.id: record for record in records}
        return tuple(by_id[value] for value in validated if value in by_id)

    def list_financial_facts(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[ProviderFinancialFactRecord, ...]:
        statement = (
            select(ProviderFinancialFact)
            .where(
                ProviderFinancialFact.security_id == security_id,
                ProviderFinancialFact.retrieved_at <= research_as_of_time,
                self._published_by(ProviderFinancialFact.source_published_at, research_as_of_time),
            )
            .order_by(
                ProviderFinancialFact.period_end.desc().nullslast(),
                ProviderFinancialFact.filed_at.desc().nullslast(),
                ProviderFinancialFact.retrieved_at.desc(),
                ProviderFinancialFact.id,
            )
        )
        if provider_id is not None:
            statement = statement.where(ProviderFinancialFact.provider_id == provider_id)
        return self._load(statement, ProviderFinancialFactRecord, limit)

    def list_financial_facts_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> tuple[ProviderFinancialFactRecord, ...]:
        validated = self._validated_ids(source_ids)
        statement = select(ProviderFinancialFact).where(
            ProviderFinancialFact.security_id == security_id,
            ProviderFinancialFact.id.in_(validated),
        )
        records = self._load(statement, ProviderFinancialFactRecord, len(validated))
        by_id = {record.id: record for record in records}
        return tuple(by_id[value] for value in validated if value in by_id)

    def list_source_documents(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
        limit: int,
        provider_id: UUID | None = None,
    ) -> tuple[SourceDocumentRecord, ...]:
        statement = (
            select(
                SourceDocument.id,
                SourceDocument.security_id,
                SourceDocument.provider_id,
                SourceDocument.source_payload_id,
                SourceDocument.provider_document_id,
                SourceDocument.document_type,
                SourceDocument.title,
                SourceDocument.form_type,
                SourceDocument.accession_number,
                SourceDocument.announcement_id,
                SourceDocument.period_end,
                SourceDocument.filed_at,
                SourceDocument.published_at,
                SourceDocument.source_url,
                SourceDocument.primary_document_name,
                SourceDocument.mime_type,
                SourceDocument.checksum,
                SourceDocument.byte_size,
                SourceDocument.document_status,
                SourceDocument.retrieved_at,
                SourceDocument.created_at,
                SourceDocument.updated_at,
            )
            .where(
                SourceDocument.security_id == security_id,
                SourceDocument.retrieved_at <= research_as_of_time,
                self._published_by(SourceDocument.published_at, research_as_of_time),
            )
            .order_by(
                SourceDocument.published_at.desc().nullslast(),
                SourceDocument.retrieved_at.desc(),
                SourceDocument.id,
            )
        )
        if provider_id is not None:
            statement = statement.where(SourceDocument.provider_id == provider_id)
        statement = statement.limit(self._validated_limit(limit))
        with self._session.no_autoflush:
            rows = self._session.execute(statement).mappings().all()
        return tuple(self._safe_record(SourceDocumentRecord, dict(row)) for row in rows)

    def get_source_document_metadata(
        self,
        document_id: UUID,
        security_id: UUID,
        research_as_of_time: datetime,
    ) -> SourceDocumentRecord | None:
        statement = (
            self._source_document_select()
            .where(
                SourceDocument.id == document_id,
                SourceDocument.security_id == security_id,
                SourceDocument.retrieved_at <= research_as_of_time,
                self._published_by(SourceDocument.published_at, research_as_of_time),
            )
            .limit(1)
        )
        with self._session.no_autoflush:
            row = self._session.execute(statement).mappings().one_or_none()
        return None if row is None else self._safe_record(SourceDocumentRecord, dict(row))

    def list_source_documents_by_ids(
        self, security_id: UUID, source_ids: tuple[UUID, ...]
    ) -> tuple[SourceDocumentRecord, ...]:
        validated = self._validated_ids(source_ids)
        statement = (
            self._source_document_select()
            .where(
                SourceDocument.security_id == security_id,
                SourceDocument.id.in_(validated),
            )
            .limit(len(validated))
        )
        with self._session.no_autoflush:
            rows = self._session.execute(statement).mappings().all()
        records = {row["id"]: self._safe_record(SourceDocumentRecord, dict(row)) for row in rows}
        return tuple(records[value] for value in validated if value in records)

    def get_snapshot(self, snapshot_id: UUID) -> DataSnapshotRecord | None:
        with self._session.no_autoflush:
            entity = self._session.get(DataSnapshot, snapshot_id)
        return None if entity is None else self._safe_record(DataSnapshotRecord, entity)

    def get_latest_eligible_snapshot(
        self, security_id: UUID, research_as_of_time: datetime
    ) -> DataSnapshotRecord | None:
        statement = (
            select(DataSnapshot)
            .where(
                DataSnapshot.security_id == security_id,
                DataSnapshot.research_as_of_time <= research_as_of_time,
                DataSnapshot.status.in_(("COMPLETE", "PARTIAL")),
            )
            .order_by(
                DataSnapshot.research_as_of_time.desc(),
                DataSnapshot.snapshot_version.desc(),
                DataSnapshot.id,
            )
            .limit(1)
        )
        with self._session.no_autoflush:
            entity = self._session.scalar(statement)
        return None if entity is None else self._safe_record(DataSnapshotRecord, entity)

    def get_latest_snapshot_at_as_of(
        self,
        security_id: UUID,
        research_as_of_time: datetime,
    ) -> DataSnapshotRecord | None:
        statement = (
            select(DataSnapshot)
            .where(
                DataSnapshot.security_id == security_id,
                DataSnapshot.research_as_of_time == research_as_of_time,
            )
            .order_by(DataSnapshot.snapshot_version.desc(), DataSnapshot.id)
            .limit(1)
        )
        with self._session.no_autoflush:
            entity = self._session.scalar(statement)
        return None if entity is None else self._safe_record(DataSnapshotRecord, entity)

    def list_snapshot_items(self, snapshot_id: UUID, limit: int) -> tuple[SnapshotItemRecord, ...]:
        statement = (
            select(SnapshotItem)
            .where(SnapshotItem.snapshot_id == snapshot_id)
            .order_by(
                SnapshotItem.category,
                SnapshotItem.source_record_type,
                SnapshotItem.source_record_id,
                SnapshotItem.id,
            )
        )
        return self._load(statement, SnapshotItemRecord, limit)

    def list_snapshot_items_by_category(
        self,
        snapshot_id: UUID,
        category: DataCategory,
        limit: int,
    ) -> tuple[SnapshotItemRecord, ...]:
        statement = (
            select(SnapshotItem)
            .where(
                SnapshotItem.snapshot_id == snapshot_id,
                SnapshotItem.category == category.value,
            )
            .order_by(
                SnapshotItem.source_record_type,
                SnapshotItem.source_record_id,
                SnapshotItem.id,
            )
        )
        return self._load(statement, SnapshotItemRecord, limit)

    def get_snapshot_evidence_aggregate(
        self, snapshot_id: UUID
    ) -> SnapshotEvidenceAggregateRecord | None:
        item_count_expression = func.count(SnapshotItem.id)
        statement = (
            select(
                item_count_expression.label("item_count"),
                func.max(SnapshotItem.retrieved_at).label("latest_retrieved_at"),
                func.array_agg(func.distinct(SnapshotItem.provider_id)).label("provider_ids"),
            )
            .where(SnapshotItem.snapshot_id == snapshot_id)
            .having(item_count_expression <= _SNAPSHOT_AGGREGATION_ITEM_LIMIT)
        )
        with self._session.no_autoflush:
            row = self._session.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        item_count = cast(int, row["item_count"])
        if item_count > _SNAPSHOT_AGGREGATION_ITEM_LIMIT:
            return None
        provider_values = cast(list[UUID] | None, row["provider_ids"])
        return self._safe_record(
            SnapshotEvidenceAggregateRecord,
            {
                "snapshot_id": snapshot_id,
                "provider_ids": tuple(sorted(provider_values or (), key=str)),
                "latest_retrieved_at": row["latest_retrieved_at"],
                "item_count": item_count,
            },
        )

    def list_snapshot_items_for_replay(self, snapshot_id: UUID) -> tuple[SnapshotItemRecord, ...]:
        statement = (
            select(SnapshotItem)
            .where(SnapshotItem.snapshot_id == snapshot_id)
            .order_by(
                SnapshotItem.category,
                SnapshotItem.source_record_type,
                SnapshotItem.source_record_id,
                SnapshotItem.id,
            )
            .limit(_SNAPSHOT_REPLAY_ITEM_LIMIT + 1)
        )
        with self._session.no_autoflush:
            entities = self._session.scalars(statement).all()
        if len(entities) > _SNAPSHOT_REPLAY_ITEM_LIMIT:
            raise StoredDataValidationError("Stored snapshot item count exceeded safe bound")
        return tuple(self._safe_record(SnapshotItemRecord, entity) for entity in entities)

    def _load(
        self,
        statement: Select[tuple[EntityT]],
        record_type: type[RecordT],
        limit: int,
    ) -> tuple[RecordT, ...]:
        bounded = statement.limit(self._validated_limit(limit))
        with self._session.no_autoflush:
            entities = self._session.scalars(bounded).all()
        return tuple(self._safe_record(record_type, entity) for entity in entities)

    @staticmethod
    def _source_document_select() -> Select[tuple[object, ...]]:
        return select(
            SourceDocument.id,
            SourceDocument.security_id,
            SourceDocument.provider_id,
            SourceDocument.source_payload_id,
            SourceDocument.provider_document_id,
            SourceDocument.document_type,
            SourceDocument.title,
            SourceDocument.form_type,
            SourceDocument.accession_number,
            SourceDocument.announcement_id,
            SourceDocument.period_end,
            SourceDocument.filed_at,
            SourceDocument.published_at,
            SourceDocument.source_url,
            SourceDocument.primary_document_name,
            SourceDocument.mime_type,
            SourceDocument.checksum,
            SourceDocument.byte_size,
            SourceDocument.document_status,
            SourceDocument.retrieved_at,
            SourceDocument.created_at,
            SourceDocument.updated_at,
        )

    @staticmethod
    def _safe_record(record_type: type[RecordT], value: object) -> RecordT:
        try:
            return record_type.model_validate(value)
        except ValidationError:
            raise StoredDataValidationError("Stored data failed safe validation") from None

    @staticmethod
    def _mapping_record(entity: ProviderInstrumentMapping) -> ProviderInstrumentMappingRecord:
        return ProviderInstrumentMappingRecord(
            id=entity.id,
            provider_id=entity.provider_id,
            security_id=entity.security_id,
            provider_symbol=entity.provider_symbol,
            provider_exchange_code=entity.provider_exchange_code,
            provider_instrument_id=entity.provider_instrument_id,
            valid_from=entity.valid_from,
            valid_to=entity.valid_to,
            is_primary=entity.is_primary,
            metadata=cast(dict[str, JsonValue], entity.mapping_metadata),
            source_name=entity.source_name,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    @staticmethod
    def _published_by(
        column: InstrumentedAttribute[datetime | None], as_of: datetime
    ) -> ColumnElement[bool]:
        return or_(column.is_(None), column <= as_of)

    @staticmethod
    def _validated_limit(limit: int) -> int:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return limit

    @staticmethod
    def _validated_ids(values: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if not 1 <= len(values) <= 100:
            raise ValueError("source IDs must be bounded between 1 and 100")
        if len(set(values)) != len(values):
            raise ValueError("source IDs must be unique")
        return values

    @staticmethod
    def _validate_ingestion_state(
        *,
        status: str,
        requested_at: datetime,
        started_at: datetime | None,
        completed_at: datetime | None,
    ) -> None:
        if started_at is not None and started_at < requested_at:
            raise ValueError("started_at cannot precede requested_at")
        if completed_at is not None and completed_at < (started_at or requested_at):
            raise ValueError("completed_at cannot precede the run start")
        if status == "QUEUED" and (started_at is not None or completed_at is not None):
            raise ValueError("QUEUED runs cannot have lifecycle timestamps")
        if status == "RUNNING" and (started_at is None or completed_at is not None):
            raise ValueError("RUNNING runs require started_at and no completed_at")
        terminal = {"PASS", "PARTIAL", "BLOCKED", "FAIL", "CANCELLED"}
        if status in terminal and completed_at is None:
            raise ValueError("terminal runs require completed_at")
