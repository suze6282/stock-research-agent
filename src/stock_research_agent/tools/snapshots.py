"""Read-only persisted snapshot tools."""

from __future__ import annotations

from uuid import UUID

from stock_research_agent.domain.data_access.enums import QualityStatus
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.data_access.schemas import (
    DataSnapshotRecord,
    SnapshotEvidenceAggregateRecord,
    SnapshotItemRecord,
)
from stock_research_agent.tools.registry import ReadOnlyToolSupport
from stock_research_agent.tools.schemas import (
    DataSnapshotData,
    DataSnapshotEnvelope,
    GetDataSnapshotInput,
    ListSnapshotItemsInput,
    SnapshotItemData,
    SnapshotItemsEnvelope,
)


def _snapshot_data(record: DataSnapshotRecord) -> DataSnapshotData:
    return DataSnapshotData(
        id=record.id,
        security_id=record.security_id,
        research_as_of_time=record.research_as_of_time,
        snapshot_version=record.snapshot_version,
        status=record.status,
        completed_at=record.completed_at,
        checksum=record.checksum,
        formula_version=record.formula_version,
        created_at=record.created_at,
    )


def _item_data(record: SnapshotItemRecord) -> SnapshotItemData:
    return SnapshotItemData(
        id=record.id,
        snapshot_id=record.snapshot_id,
        provider_id=record.provider_id,
        category=record.category,
        source_record_type=record.source_record_type,
        source_record_id=record.source_record_id,
        source_published_at=record.source_published_at,
        retrieved_at=record.retrieved_at,
        checksum=record.checksum,
        created_at=record.created_at,
    )


class GetDataSnapshotTool(ReadOnlyToolSupport):
    def __init__(self, query_service: DataAccessQueryService) -> None:
        super().__init__(query_service)

    def __call__(self, request: GetDataSnapshotInput) -> DataSnapshotEnvelope:
        try:
            result = self._query_service.snapshot(request.snapshot_id)
        except Exception:
            return self.envelope(
                DataSnapshotEnvelope,
                tool_name="get_data_snapshot",
                status=QualityStatus.FAIL,
                data=(),
                source_record_ids=(),
                provider_ids=(),
                snapshot_id=request.snapshot_id,
                research_as_of_time=None,
                retrieved_at=None,
                warnings=("DATA_ACCESS_QUERY_FAILED",),
            )
        if not result.records:
            return self.envelope(
                DataSnapshotEnvelope,
                tool_name="get_data_snapshot",
                status=QualityStatus.BLOCKED,
                data=(),
                source_record_ids=(),
                provider_ids=(),
                snapshot_id=request.snapshot_id,
                research_as_of_time=None,
                retrieved_at=None,
                warnings=("SNAPSHOT_NOT_FOUND",),
            )
        snapshot = result.records[0]
        status_mapping = {
            "COMPLETE": QualityStatus.PASS,
            "PARTIAL": QualityStatus.PARTIAL,
            "FAILED": QualityStatus.FAIL,
            "BUILDING": QualityStatus.BLOCKED,
            "SUPERSEDED": QualityStatus.BLOCKED,
        }
        warning_mapping = {
            "COMPLETE": (),
            "PARTIAL": ("SNAPSHOT_PARTIAL",),
            "FAILED": ("SNAPSHOT_FAILED",),
            "BUILDING": ("SNAPSHOT_NOT_TERMINAL",),
            "SUPERSEDED": ("SNAPSHOT_NOT_READABLE",),
        }
        try:
            aggregate_result = self._query_service.snapshot_evidence_aggregate(request.snapshot_id)
        except Exception:
            return self.envelope(
                DataSnapshotEnvelope,
                tool_name="get_data_snapshot",
                status=QualityStatus.FAIL,
                data=(),
                source_record_ids=(),
                provider_ids=(),
                snapshot_id=request.snapshot_id,
                research_as_of_time=None,
                retrieved_at=None,
                warnings=("DATA_ACCESS_QUERY_FAILED",),
            )
        if not aggregate_result.records:
            return self.envelope(
                DataSnapshotEnvelope,
                tool_name="get_data_snapshot",
                status=QualityStatus.FAIL,
                data=(),
                source_record_ids=(),
                provider_ids=(),
                snapshot_id=request.snapshot_id,
                research_as_of_time=None,
                retrieved_at=None,
                warnings=aggregate_result.warnings,
            )
        aggregate = aggregate_result.records[0]
        if not self._aggregate_is_consistent(aggregate, request.snapshot_id):
            return self.envelope(
                DataSnapshotEnvelope,
                tool_name="get_data_snapshot",
                status=QualityStatus.FAIL,
                data=(),
                source_record_ids=(),
                provider_ids=(),
                snapshot_id=request.snapshot_id,
                research_as_of_time=None,
                retrieved_at=None,
                warnings=("SNAPSHOT_AGGREGATION_INCONSISTENT",),
            )
        return self.envelope(
            DataSnapshotEnvelope,
            tool_name="get_data_snapshot",
            status=status_mapping[snapshot.status],
            data=(_snapshot_data(snapshot),),
            source_record_ids=(snapshot.id,),
            provider_ids=aggregate.provider_ids,
            snapshot_id=request.snapshot_id,
            research_as_of_time=None,
            retrieved_at=aggregate.latest_retrieved_at,
            warnings=warning_mapping[snapshot.status],
        )

    @staticmethod
    def _aggregate_is_consistent(
        aggregate: SnapshotEvidenceAggregateRecord,
        snapshot_id: UUID,
    ) -> bool:
        if aggregate.snapshot_id != snapshot_id or not 0 <= aggregate.item_count <= 396:
            return False
        if aggregate.item_count == 0:
            return not aggregate.provider_ids and aggregate.latest_retrieved_at is None
        return (
            bool(aggregate.provider_ids)
            and aggregate.latest_retrieved_at is not None
            and len(set(aggregate.provider_ids)) == len(aggregate.provider_ids)
            and aggregate.provider_ids == tuple(sorted(aggregate.provider_ids, key=str))
            and len(aggregate.provider_ids) <= aggregate.item_count
        )


class ListSnapshotItemsTool(ReadOnlyToolSupport):
    def __init__(self, query_service: DataAccessQueryService) -> None:
        super().__init__(query_service)

    def __call__(self, request: ListSnapshotItemsInput) -> SnapshotItemsEnvelope:
        try:
            snapshot_result = self._query_service.snapshot(request.snapshot_id)
            if not snapshot_result.records:
                return self._empty(request, QualityStatus.BLOCKED, ("SNAPSHOT_NOT_FOUND",))
            snapshot = snapshot_result.records[0]
            if snapshot.status == "FAILED":
                return self._empty(request, QualityStatus.FAIL, ("SNAPSHOT_FAILED",))
            if snapshot.status not in {"COMPLETE", "PARTIAL"}:
                return self._empty(request, QualityStatus.BLOCKED, ("SNAPSHOT_NOT_TERMINAL",))
            result = self._query_service.snapshot_items(request.snapshot_id, request.limit)
        except Exception:
            return self._empty(request, QualityStatus.FAIL, ("DATA_ACCESS_QUERY_FAILED",))
        records = result.records
        warnings = list(result.warnings)
        status = result.status
        if snapshot.status == "PARTIAL":
            warnings.append("SNAPSHOT_PARTIAL")
            if status is QualityStatus.PASS:
                status = QualityStatus.PARTIAL
        return self.envelope(
            SnapshotItemsEnvelope,
            tool_name="list_snapshot_items",
            status=status,
            data=tuple(_item_data(record) for record in records),
            source_record_ids=tuple(record.source_record_id for record in records),
            provider_ids=tuple(dict.fromkeys(record.provider_id for record in records)),
            snapshot_id=request.snapshot_id,
            research_as_of_time=None,
            retrieved_at=max((record.retrieved_at for record in records), default=None),
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def _empty(
        self,
        request: ListSnapshotItemsInput,
        status: QualityStatus,
        warnings: tuple[str, ...],
    ) -> SnapshotItemsEnvelope:
        return self.envelope(
            SnapshotItemsEnvelope,
            tool_name="list_snapshot_items",
            status=status,
            data=(),
            source_record_ids=(),
            provider_ids=(),
            snapshot_id=request.snapshot_id,
            research_as_of_time=None,
            retrieved_at=None,
            warnings=warnings,
        )


__all__ = ["GetDataSnapshotTool", "ListSnapshotItemsTool"]
