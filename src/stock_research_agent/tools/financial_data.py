"""Read-only persisted financial-data tools."""

from __future__ import annotations

from datetime import date, datetime
from typing import cast
from uuid import UUID

from stock_research_agent.domain.data_access.enums import DataCategory
from stock_research_agent.domain.data_access.queries import DataAccessQueryService
from stock_research_agent.domain.data_access.schemas import ProviderFinancialFactRecord
from stock_research_agent.tools.registry import ReadOnlyToolSupport
from stock_research_agent.tools.schemas import (
    GetReportedFinancialFactsInput,
    ReportedFinancialFactData,
    ReportedFinancialFactsEnvelope,
)


def _sorted_facts(
    records: tuple[ProviderFinancialFactRecord, ...],
) -> tuple[ProviderFinancialFactRecord, ...]:
    ordered = sorted(records, key=lambda record: str(record.id))
    ordered.sort(key=lambda record: record.retrieved_at, reverse=True)
    ordered.sort(key=lambda record: record.filed_at or record.retrieved_at, reverse=True)
    ordered.sort(key=lambda record: record.period_end or date.min, reverse=True)
    return tuple(ordered)


def _fact_data(record: ProviderFinancialFactRecord) -> ReportedFinancialFactData:
    return ReportedFinancialFactData(
        id=record.id,
        security_id=record.security_id,
        provider_id=record.provider_id,
        document_id=record.document_id,
        statement_type=record.statement_type,
        provider_concept=record.provider_concept,
        reported_label=record.reported_label,
        taxonomy=record.taxonomy,
        context_id=record.context_id,
        dimensions=record.dimensions,
        value=record.value,
        unit=record.unit,
        currency_code=record.currency_code,
        fiscal_year=record.fiscal_year,
        fiscal_quarter=record.fiscal_quarter,
        fiscal_period=record.fiscal_period,
        period_start=record.period_start,
        period_end=record.period_end,
        instant_date=record.instant_date,
        filed_at=record.filed_at,
        source_published_at=record.source_published_at,
        form_type=record.form_type,
        is_annual=record.is_annual,
        is_cumulative=record.is_cumulative,
        is_audited=record.is_audited,
        is_restated=record.is_restated,
        provider_record_id=record.provider_record_id,
        retrieved_at=record.retrieved_at,
    )


class GetReportedFinancialFactsTool(ReadOnlyToolSupport):
    def __init__(self, query_service: DataAccessQueryService) -> None:
        super().__init__(query_service)

    def __call__(self, request: GetReportedFinancialFactsInput) -> ReportedFinancialFactsEnvelope:
        selection = self.select_evidence(
            request,
            category=DataCategory.FINANCIAL_FACTS,
            source_record_type="provider_financial_facts",
            as_of_reader=lambda: self._query_service.reported_financial_facts(
                request.security_id,
                cast(datetime, request.research_as_of_time),
                request.limit,
            ),
            snapshot_reader=lambda source_ids: self._query_service.financial_facts_by_ids(
                request.security_id,
                source_ids,
            ),
        )
        records = _sorted_facts(selection.records)[: request.limit]
        provider_ids: tuple[UUID, ...] = tuple(
            dict.fromkeys(record.provider_id for record in records)
        )
        return self.envelope(
            ReportedFinancialFactsEnvelope,
            tool_name="get_reported_financial_facts",
            status=selection.status,
            data=tuple(_fact_data(record) for record in records),
            source_record_ids=tuple(record.id for record in records),
            provider_ids=self.selection_provider_ids(selection, provider_ids),
            snapshot_id=selection.snapshot_id,
            research_as_of_time=selection.research_as_of_time,
            retrieved_at=max((record.retrieved_at for record in records), default=None),
            warnings=selection.warnings,
        )


__all__ = ["GetReportedFinancialFactsTool"]
