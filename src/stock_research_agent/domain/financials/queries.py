"""Read-only query service for persisted Stage 5 financial outputs."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from stock_research_agent.domain.financials.enums import QualityStatus
from stock_research_agent.domain.financials.repositories import FinancialReadRepository
from stock_research_agent.domain.financials.schemas import (
    CalculationInputRecord,
    CalculationRunDetail,
    DerivedMetricRecord,
    FinancialPeriodRecord,
    NormalizedFinancialFactRecord,
)


@dataclass(frozen=True, slots=True)
class FinancialQueryResult[RecordT]:
    status: QualityStatus
    records: tuple[RecordT, ...]
    warnings: tuple[str, ...]


class FinancialQueryService:
    def __init__(self, repository: FinancialReadRepository) -> None:
        self._repository = repository

    def periods(
        self,
        security_id: UUID,
        snapshot_id: UUID,
        period_type: str | None,
        limit: int,
    ) -> FinancialQueryResult[FinancialPeriodRecord]:
        return _result(
            self._repository.read_financial_periods(security_id, snapshot_id, period_type, limit),
            "FINANCIAL_PERIODS_NOT_FOUND",
        )

    def provenance(self, snapshot_id: UUID) -> tuple[str, str, str]:
        return self._repository.read_snapshot_provenance(snapshot_id)

    def facts(
        self,
        security_id: UUID,
        snapshot_id: UUID,
        concept_code: str | None,
        limit: int,
    ) -> FinancialQueryResult[NormalizedFinancialFactRecord]:
        return _result(
            self._repository.read_normalized_financial_facts(
                security_id, snapshot_id, concept_code, limit
            ),
            "NORMALIZED_FINANCIAL_FACTS_NOT_FOUND",
        )

    def metrics(
        self,
        security_id: UUID,
        snapshot_id: UUID,
        metric_code: str | None,
        limit: int,
    ) -> FinancialQueryResult[DerivedMetricRecord]:
        return _result(
            self._repository.read_financial_metrics(security_id, snapshot_id, metric_code, limit),
            "FINANCIAL_METRICS_NOT_FOUND",
        )

    def lineage(
        self,
        calculation_run_id: UUID,
        metric_code: str,
        limit: int = 100,
    ) -> FinancialQueryResult[CalculationInputRecord]:
        return _result(
            self._repository.read_metric_lineage(calculation_run_id, metric_code, limit),
            "METRIC_LINEAGE_NOT_FOUND",
        )

    def calculation_run(self, calculation_run_id: UUID) -> CalculationRunDetail | None:
        return self._repository.read_calculation_run(calculation_run_id)


def _result[RecordT](records: tuple[RecordT, ...], warning: str) -> FinancialQueryResult[RecordT]:
    if not records:
        return FinancialQueryResult(QualityStatus.BLOCKED, (), (warning,))
    return FinancialQueryResult(QualityStatus.PASS, records, ())
