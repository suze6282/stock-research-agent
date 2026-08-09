"""Read-only persisted source-document metadata tools."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from stock_research_agent.domain.data_access.enums import DataCategory, QualityStatus
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.data_access.schemas import SourceDocumentRecord
from stock_research_agent.tools.registry import EvidenceSelection, ReadOnlyToolSupport
from stock_research_agent.tools.schemas import (
    GetSourceDocumentMetadataInput,
    ListSourceDocumentsInput,
    SourceDocumentMetadataData,
    SourceDocumentMetadataEnvelope,
    SourceDocumentsEnvelope,
)


def _sorted_documents(
    records: tuple[SourceDocumentRecord, ...],
) -> tuple[SourceDocumentRecord, ...]:
    ordered = sorted(records, key=lambda record: str(record.id))
    ordered.sort(key=lambda record: record.retrieved_at, reverse=True)
    ordered.sort(key=lambda record: record.published_at or record.retrieved_at, reverse=True)
    return tuple(ordered)


def _document_data(record: SourceDocumentRecord) -> SourceDocumentMetadataData:
    return SourceDocumentMetadataData(
        id=record.id,
        security_id=record.security_id,
        provider_id=record.provider_id,
        provider_document_id=record.provider_document_id,
        document_type=record.document_type,
        title=record.title,
        form_type=record.form_type,
        accession_number=record.accession_number,
        announcement_id=record.announcement_id,
        period_end=record.period_end,
        filed_at=record.filed_at,
        published_at=record.published_at,
        source_url=record.source_url,
        primary_document_name=record.primary_document_name,
        mime_type=record.mime_type,
        checksum=record.checksum,
        byte_size=record.byte_size,
        document_status=record.document_status,
        retrieved_at=record.retrieved_at,
    )


class ListSourceDocumentsTool(ReadOnlyToolSupport):
    def __init__(self, query_service: DataAccessQueryService) -> None:
        super().__init__(query_service)

    def __call__(self, request: ListSourceDocumentsInput) -> SourceDocumentsEnvelope:
        selection = self.select_evidence(
            request,
            category=DataCategory.FILING_METADATA,
            source_record_type="source_documents",
            as_of_reader=lambda: self._query_service.source_documents(
                request.security_id,
                cast(datetime, request.research_as_of_time),
                request.limit,
            ),
            snapshot_reader=lambda source_ids: self._query_service.source_documents_by_ids(
                request.security_id,
                source_ids,
            ),
        )
        records = _sorted_documents(selection.records)[: request.limit]
        return self.envelope(
            SourceDocumentsEnvelope,
            tool_name="list_source_documents",
            status=selection.status,
            data=tuple(_document_data(record) for record in records),
            source_record_ids=tuple(record.id for record in records),
            provider_ids=self.selection_provider_ids(
                selection,
                tuple(dict.fromkeys(record.provider_id for record in records)),
            ),
            snapshot_id=selection.snapshot_id,
            research_as_of_time=selection.research_as_of_time,
            retrieved_at=max((record.retrieved_at for record in records), default=None),
            warnings=selection.warnings,
        )


class GetSourceDocumentMetadataTool(ReadOnlyToolSupport):
    def __init__(self, query_service: DataAccessQueryService) -> None:
        super().__init__(query_service)

    def __call__(self, request: GetSourceDocumentMetadataInput) -> SourceDocumentMetadataEnvelope:
        if request.research_as_of_time is not None:
            selection = self._as_of_selection(request)
        else:
            selection = self._snapshot_selection(request)
        records = tuple(record for record in selection.records if record.id == request.document_id)[
            :1
        ]
        return self.envelope(
            SourceDocumentMetadataEnvelope,
            tool_name="get_source_document_metadata",
            status=selection.status,
            data=tuple(_document_data(record) for record in records),
            source_record_ids=tuple(record.id for record in records),
            provider_ids=self.selection_provider_ids(
                selection,
                tuple(record.provider_id for record in records),
            ),
            snapshot_id=selection.snapshot_id,
            research_as_of_time=selection.research_as_of_time,
            retrieved_at=max((record.retrieved_at for record in records), default=None),
            warnings=selection.warnings,
        )

    def _as_of_selection(
        self, request: GetSourceDocumentMetadataInput
    ) -> EvidenceSelection[SourceDocumentRecord]:
        try:
            result = self._query_service.source_document_metadata(
                request.document_id,
                request.security_id,
                cast(datetime, request.research_as_of_time),
            )
        except Exception:
            return EvidenceSelection(
                status=QualityStatus.FAIL,
                records=(),
                warnings=("DATA_ACCESS_QUERY_FAILED",),
                snapshot_id=None,
                research_as_of_time=request.research_as_of_time,
            )
        return EvidenceSelection(
            status=result.status,
            records=result.records,
            warnings=result.warnings,
            snapshot_id=None,
            research_as_of_time=request.research_as_of_time,
        )

    def _snapshot_selection(
        self, request: GetSourceDocumentMetadataInput
    ) -> EvidenceSelection[SourceDocumentRecord]:
        snapshot_id = cast(UUID, request.snapshot_id)
        try:
            snapshot_result = self._query_service.snapshot(snapshot_id)
        except Exception:
            return self._document_failure(snapshot_id)
        if not snapshot_result.records:
            return EvidenceSelection(
                status=QualityStatus.BLOCKED,
                records=(),
                warnings=("SNAPSHOT_NOT_FOUND",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        snapshot = snapshot_result.records[0]
        if snapshot.security_id != request.security_id:
            return EvidenceSelection(
                status=QualityStatus.BLOCKED,
                records=(),
                warnings=("SNAPSHOT_SECURITY_MISMATCH",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        if snapshot.status == "FAILED":
            return EvidenceSelection(
                status=QualityStatus.FAIL,
                records=(),
                warnings=("SNAPSHOT_FAILED",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        if snapshot.status not in {"COMPLETE", "PARTIAL"}:
            return EvidenceSelection(
                status=QualityStatus.BLOCKED,
                records=(),
                warnings=("SNAPSHOT_NOT_TERMINAL",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        try:
            item_result = self._query_service.snapshot_items_by_category(
                snapshot_id,
                DataCategory.FILING_METADATA,
                100,
            )
        except Exception:
            return self._document_failure(snapshot_id)
        matching = tuple(
            item
            for item in item_result.records
            if item.source_record_type == "source_documents"
            and item.source_record_id == request.document_id
        )
        if not matching:
            return EvidenceSelection(
                status=QualityStatus.BLOCKED,
                records=(),
                warnings=("DOCUMENT_NOT_IN_SNAPSHOT",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        try:
            result = self._query_service.source_documents_by_ids(
                request.security_id,
                (request.document_id,),
            )
        except Exception:
            return self._document_failure(snapshot_id)
        if not result.records:
            return EvidenceSelection(
                status=QualityStatus.PARTIAL,
                records=(),
                warnings=("SNAPSHOT_DOCUMENT_UNAVAILABLE",),
                snapshot_id=snapshot_id,
                research_as_of_time=None,
            )
        warnings = list(result.warnings)
        if snapshot.status == "PARTIAL":
            warnings.append("SNAPSHOT_PARTIAL")
        status = result.status
        if warnings and status is QualityStatus.PASS:
            status = QualityStatus.PARTIAL
        return EvidenceSelection(
            status=status,
            records=result.records,
            warnings=tuple(dict.fromkeys(warnings)),
            snapshot_id=snapshot_id,
            research_as_of_time=None,
        )

    @staticmethod
    def _document_failure(
        snapshot_id: UUID | None,
    ) -> EvidenceSelection[SourceDocumentRecord]:
        return EvidenceSelection(
            status=QualityStatus.FAIL,
            records=(),
            warnings=("DATA_ACCESS_QUERY_FAILED",),
            snapshot_id=snapshot_id,
            research_as_of_time=None,
        )


__all__ = ["GetSourceDocumentMetadataTool", "ListSourceDocumentsTool"]
