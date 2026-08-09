"""Read-only tools for persisted normalized financial facts and calculations."""

from __future__ import annotations

from dataclasses import asdict
from typing import cast

from stock_research_agent.domain.data_access.enums import QualityStatus as ToolQualityStatus
from stock_research_agent.domain.financials.enums import QualityStatus
from stock_research_agent.domain.financials.queries import FinancialQueryService
from stock_research_agent.tools.schemas import (
    CalculationRunData,
    CalculationRunEnvelope,
    EvidenceAccessMode,
    EvidenceLiveStatus,
    EvidenceOrigin,
    FinancialMetricData,
    FinancialMetricsEnvelope,
    FinancialPeriodData,
    FinancialPeriodsEnvelope,
    GetCalculationRunInput,
    GetFinancialMetricsInput,
    GetFinancialPeriodsInput,
    GetMetricDetailInput,
    GetMetricLineageInput,
    GetNormalizedFinancialFactsInput,
    MetricDetailEnvelope,
    MetricLineageData,
    MetricLineageEnvelope,
    NormalizedFinancialFactData,
    NormalizedFinancialFactsEnvelope,
    ToolProvenance,
    ToolQuality,
)


def _provenance(service: FinancialQueryService, snapshot_id: object) -> ToolProvenance:
    from uuid import UUID

    if not isinstance(snapshot_id, UUID):
        return ToolProvenance(
            data_origin="UNKNOWN",
            access_mode="UNKNOWN",
            live_status="UNKNOWN",
        )
    origin, access, live = service.provenance(snapshot_id)
    return ToolProvenance(
        data_origin=cast(EvidenceOrigin, origin),
        access_mode=cast(EvidenceAccessMode, access),
        live_status=cast(EvidenceLiveStatus, live),
    )


def _tool_status(status: QualityStatus) -> ToolQualityStatus:
    return ToolQualityStatus(status.value)


class GetFinancialPeriodsTool:
    def __init__(self, service: FinancialQueryService) -> None:
        self._service = service

    def __call__(self, request: GetFinancialPeriodsInput) -> FinancialPeriodsEnvelope:
        result = self._service.periods(
            request.security_id,
            request.snapshot_id,
            request.period_type,
            request.limit,
        )
        data = tuple(FinancialPeriodData(**asdict(record)) for record in result.records)
        status = _tool_status(result.status)
        return FinancialPeriodsEnvelope(
            tool_name="get_financial_periods",
            tool_version="1.0.0",
            status=status.value,
            data=data,
            source_record_ids=tuple(record.id for record in result.records),
            snapshot_id=request.snapshot_id,
            warnings=result.warnings,
            quality=ToolQuality(status=status, record_count=len(data)),
            provenance=_provenance(self._service, request.snapshot_id),
        )


class GetNormalizedFinancialFactsTool:
    def __init__(self, service: FinancialQueryService) -> None:
        self._service = service

    def __call__(
        self, request: GetNormalizedFinancialFactsInput
    ) -> NormalizedFinancialFactsEnvelope:
        result = self._service.facts(
            request.security_id,
            request.snapshot_id,
            request.concept_code,
            request.limit,
        )
        data = tuple(NormalizedFinancialFactData(**asdict(record)) for record in result.records)
        status = _tool_status(result.status)
        return NormalizedFinancialFactsEnvelope(
            tool_name="get_normalized_financial_facts",
            tool_version="1.0.0",
            status=status.value,
            data=data,
            source_record_ids=tuple(record.source_financial_fact_id for record in result.records),
            snapshot_id=request.snapshot_id,
            warnings=result.warnings,
            quality=ToolQuality(status=status, record_count=len(data)),
            provenance=_provenance(self._service, request.snapshot_id),
        )


def _metric_data(record: object) -> FinancialMetricData:
    from stock_research_agent.domain.financials.schemas import DerivedMetricRecord

    assert isinstance(record, DerivedMetricRecord)
    values = asdict(record)
    values["quality_status"] = record.quality_status.value
    return FinancialMetricData(**values)


def _metric_status(records: tuple[object, ...], fallback: QualityStatus) -> QualityStatus:
    from stock_research_agent.domain.financials.schemas import DerivedMetricRecord

    metrics = tuple(record for record in records if isinstance(record, DerivedMetricRecord))
    if not metrics:
        return fallback
    statuses = {metric.quality_status for metric in metrics}
    if statuses == {QualityStatus.BLOCKED}:
        return QualityStatus.BLOCKED
    if QualityStatus.BLOCKED in statuses or QualityStatus.PARTIAL in statuses:
        return QualityStatus.PARTIAL
    return QualityStatus.PASS


class GetFinancialMetricsTool:
    def __init__(self, service: FinancialQueryService) -> None:
        self._service = service

    def __call__(self, request: GetFinancialMetricsInput) -> FinancialMetricsEnvelope:
        result = self._service.metrics(
            request.security_id,
            request.snapshot_id,
            request.metric_code,
            request.limit,
        )
        data = tuple(_metric_data(record) for record in result.records)
        domain_status = _metric_status(result.records, result.status)
        status = _tool_status(domain_status)
        run_ids = tuple(dict.fromkeys(record.calculation_run_id for record in result.records))
        versions = tuple(dict.fromkeys(record.formula_version for record in result.records))
        warnings = tuple(
            dict.fromkeys(
                (
                    *result.warnings,
                    *(code for record in result.records for code in record.warning_codes),
                )
            )
        )
        return FinancialMetricsEnvelope(
            tool_name="get_financial_metrics",
            tool_version="1.0.0",
            status=status.value,
            data=data,
            source_record_ids=tuple(record.id for record in result.records),
            snapshot_id=request.snapshot_id,
            calculation_run_id=run_ids[0] if len(run_ids) == 1 else None,
            formula_version=versions[0] if len(versions) == 1 else None,
            warnings=warnings,
            quality=ToolQuality(status=status, record_count=len(data)),
            provenance=_provenance(self._service, request.snapshot_id),
        )


class GetMetricDetailTool:
    def __init__(self, service: FinancialQueryService) -> None:
        self._service = service

    def __call__(self, request: GetMetricDetailInput) -> MetricDetailEnvelope:
        result = self._service.metrics(
            request.security_id,
            request.snapshot_id,
            request.metric_code,
            1,
        )
        data = tuple(_metric_data(record) for record in result.records)
        domain_status = _metric_status(result.records, result.status)
        status = _tool_status(domain_status)
        record = result.records[0] if result.records else None
        return MetricDetailEnvelope(
            tool_name="get_metric_detail",
            tool_version="1.0.0",
            status=status.value,
            data=data,
            source_record_ids=tuple(item.id for item in result.records),
            snapshot_id=request.snapshot_id,
            calculation_run_id=record.calculation_run_id if record else None,
            formula_version=record.formula_version if record else None,
            warnings=((*result.warnings, *record.warning_codes) if record else result.warnings),
            quality=ToolQuality(status=status, record_count=len(data)),
            provenance=_provenance(self._service, request.snapshot_id),
        )


class GetMetricLineageTool:
    def __init__(self, service: FinancialQueryService) -> None:
        self._service = service

    def __call__(self, request: GetMetricLineageInput) -> MetricLineageEnvelope:
        result = self._service.lineage(
            request.calculation_run_id,
            request.metric_code,
        )
        run = self._service.calculation_run(request.calculation_run_id)
        data = tuple(MetricLineageData(**asdict(record)) for record in result.records)
        status = _tool_status(result.status)
        return MetricLineageEnvelope(
            tool_name="get_metric_lineage",
            tool_version="1.0.0",
            status=status.value,
            data=data,
            source_record_ids=tuple(
                record.normalized_fact_id
                for record in result.records
                if record.normalized_fact_id is not None
            ),
            snapshot_id=run.snapshot_id if run else None,
            calculation_run_id=request.calculation_run_id,
            warnings=result.warnings,
            quality=ToolQuality(status=status, record_count=len(data)),
            provenance=_provenance(self._service, run.snapshot_id if run else None),
        )


class GetCalculationRunTool:
    def __init__(self, service: FinancialQueryService) -> None:
        self._service = service

    def __call__(self, request: GetCalculationRunInput) -> CalculationRunEnvelope:
        record = self._service.calculation_run(request.calculation_run_id)
        warnings: tuple[str, ...]
        if record is None:
            data: tuple[CalculationRunData, ...] = ()
            status = ToolQualityStatus.BLOCKED
            warnings = ("CALCULATION_RUN_NOT_FOUND",)
            snapshot_id = None
        else:
            values = asdict(record)
            values["status"] = record.status.value
            data = (CalculationRunData(**values),)
            status = _tool_status(record.status)
            warnings = ()
            snapshot_id = record.snapshot_id
        return CalculationRunEnvelope(
            tool_name="get_calculation_run",
            tool_version="1.0.0",
            status=status.value,
            data=data,
            source_record_ids=(request.calculation_run_id,) if record else (),
            snapshot_id=snapshot_id,
            calculation_run_id=request.calculation_run_id,
            warnings=warnings,
            quality=ToolQuality(status=status, record_count=len(data)),
            provenance=_provenance(self._service, snapshot_id),
        )


__all__ = [
    "GetCalculationRunTool",
    "GetFinancialMetricsTool",
    "GetFinancialPeriodsTool",
    "GetMetricDetailTool",
    "GetMetricLineageTool",
    "GetNormalizedFinancialFactsTool",
]
