from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from stock_research_agent.domain.financials.calculation_service import (
    MetricCalculationService,
)
from stock_research_agent.domain.financials.enums import QualityStatus
from stock_research_agent.domain.financials.formulas import FORMULA_REGISTRY
from stock_research_agent.domain.financials.schemas import (
    CalculationInputWrite,
    CalculationRunRecord,
    CalculationRunWrite,
    CalculationSnapshot,
    DerivedMetricWrite,
    NormalizedFactForCalculation,
)

SNAPSHOT_ID = UUID("90000000-0000-0000-0000-000000000001")
SECURITY_ID = UUID("40000000-0000-0000-0000-000000000001")
RUN_ID = UUID("a0000000-0000-0000-0000-000000000001")
AS_OF = datetime(2026, 7, 13, tzinfo=UTC)


class EmptyCalculationRepository:
    def __init__(self, facts: tuple[NormalizedFactForCalculation, ...] = ()) -> None:
        self.facts = facts
        self.runs: list[CalculationRunWrite] = []
        self.metrics: list[DerivedMetricWrite] = []
        self.inputs: list[CalculationInputWrite] = []
        self.completed: list[tuple[UUID, QualityStatus, int]] = []
        self.locks: list[tuple[UUID, str]] = []

    def acquire_calculation_lock(self, snapshot_id: UUID, input_checksum: str) -> None:
        self.locks.append((snapshot_id, input_checksum))

    def get_snapshot_for_calculation(self, snapshot_id: UUID) -> CalculationSnapshot | None:
        assert snapshot_id == SNAPSHOT_ID
        return CalculationSnapshot(
            snapshot_id=SNAPSHOT_ID,
            security_id=SECURITY_ID,
            research_as_of_time=AS_OF,
            status="PARTIAL",
        )

    def list_normalized_facts_for_calculation(
        self, snapshot_id: UUID
    ) -> tuple[NormalizedFactForCalculation, ...]:
        assert snapshot_id == SNAPSHOT_ID
        return self.facts

    def find_calculation_run(
        self,
        snapshot_id: UUID,
        input_checksum: str,
        calculation_version: str,
        formula_set_version: str,
        mapping_version: str,
        normalization_version: str,
    ) -> CalculationRunRecord | None:
        return None

    def create_calculation_run(self, value: CalculationRunWrite) -> UUID:
        self.runs.append(value)
        return RUN_ID

    def get_formula_definition_id(self, metric_code: str, formula_version: str) -> UUID:
        number = next(
            index
            for index, definition in enumerate(FORMULA_REGISTRY, start=1)
            if definition.metric_code.value == metric_code
        )
        return UUID(f"a1000000-0000-0000-0000-{number:012d}")

    def add_derived_metric(self, value: DerivedMetricWrite) -> UUID:
        self.metrics.append(value)
        return UUID(f"a2000000-0000-0000-0000-{len(self.metrics):012d}")

    def add_calculation_input(self, value: CalculationInputWrite) -> UUID:
        self.inputs.append(value)
        return UUID(f"a3000000-0000-0000-0000-{len(self.inputs):012d}")

    def complete_calculation_run(
        self,
        calculation_run_id: UUID,
        status: QualityStatus,
        warning_count: int,
    ) -> None:
        self.completed.append((calculation_run_id, status, warning_count))


def test_empty_snapshot_creates_reusable_blocked_run_without_fake_values() -> None:
    repository = EmptyCalculationRepository()

    result = MetricCalculationService().calculate_snapshot(SNAPSHOT_ID, repository)

    assert result.calculation_run_id == RUN_ID
    assert result.status is QualityStatus.BLOCKED
    assert result.metric_count == len(FORMULA_REGISTRY)
    assert len(repository.metrics) == len(FORMULA_REGISTRY)
    assert all(metric.value is None for metric in repository.metrics)
    assert all(metric.value_state == "NULL" for metric in repository.metrics)
    assert all(metric.quality_status is QualityStatus.BLOCKED for metric in repository.metrics)
    assert all(
        metric.warning_codes == ("NO_NORMALIZED_FINANCIAL_FACTS",) for metric in repository.metrics
    )
    assert repository.completed == [(RUN_ID, QualityStatus.BLOCKED, len(FORMULA_REGISTRY))]


def test_empty_input_checksum_is_stable() -> None:
    first = EmptyCalculationRepository()
    second = EmptyCalculationRepository()

    MetricCalculationService().calculate_snapshot(SNAPSHOT_ID, first)
    MetricCalculationService().calculate_snapshot(SNAPSHOT_ID, second)

    assert first.runs[0].input_checksum == second.runs[0].input_checksum
    assert len(first.runs[0].input_checksum) == 64


def _fact(number: int, concept: str, value: str) -> NormalizedFactForCalculation:
    return NormalizedFactForCalculation(
        id=UUID(f"b0000000-0000-0000-0000-{number:012d}"),
        canonical_concept_code=concept,
        financial_period_id=UUID("b1000000-0000-0000-0000-000000000001"),
        fiscal_year=2025,
        fiscal_quarter=None,
        fiscal_period="FY",
        period_type="ANNUAL",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        duration_days=365,
        accounting_standard="US_GAAP",
        is_cumulative=True,
        is_single_quarter=False,
        normalized_value=Decimal(value),
        normalized_unit="ONE",
        currency_code="USD",
        source_published_at=datetime(2026, 2, 1, tzinfo=UTC),
    )


def test_available_same_period_facts_calculate_metrics_and_persist_lineage() -> None:
    repository = EmptyCalculationRepository(
        (
            _fact(1, "REVENUE", "100"),
            _fact(2, "COST_OF_REVENUE", "60"),
            _fact(3, "OPERATING_INCOME", "15"),
        )
    )

    result = MetricCalculationService().calculate_snapshot(SNAPSHOT_ID, repository)

    assert result.status is QualityStatus.PARTIAL
    by_code = {metric.metric_code: metric for metric in repository.metrics}
    assert by_code["gross_margin"].value == Decimal("0.4")
    assert by_code["gross_margin"].quality_status is QualityStatus.PASS
    assert by_code["operating_margin"].value == Decimal("0.15")
    assert by_code["net_margin_parent"].value is None
    assert by_code["net_margin_parent"].quality_status is QualityStatus.BLOCKED
    gross_inputs = [item for item in repository.inputs if item.metric_code == "gross_margin"]
    assert {item.input_role for item in gross_inputs} == {"revenue", "cost_of_revenue"}


def test_ttm_bridge_is_selected_and_persisted_with_method_lineage() -> None:
    facts = (
        _fact(10, "REVENUE", "100"),
        NormalizedFactForCalculation(
            id=UUID("b0000000-0000-0000-0000-000000000011"),
            canonical_concept_code="REVENUE",
            financial_period_id=UUID("b1000000-0000-0000-0000-000000000011"),
            fiscal_year=2026,
            fiscal_quarter=2,
            fiscal_period="H1",
            period_type="HALF_YEAR",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 6, 30),
            duration_days=181,
            accounting_standard="US_GAAP",
            is_cumulative=True,
            is_single_quarter=False,
            normalized_value=Decimal("60"),
            normalized_unit="ONE",
            currency_code="USD",
            source_published_at=datetime(2026, 7, 1, tzinfo=UTC),
        ),
        NormalizedFactForCalculation(
            id=UUID("b0000000-0000-0000-0000-000000000012"),
            canonical_concept_code="REVENUE",
            financial_period_id=UUID("b1000000-0000-0000-0000-000000000012"),
            fiscal_year=2025,
            fiscal_quarter=2,
            fiscal_period="H1",
            period_type="HALF_YEAR",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 6, 30),
            duration_days=181,
            accounting_standard="US_GAAP",
            is_cumulative=True,
            is_single_quarter=False,
            normalized_value=Decimal("40"),
            normalized_unit="ONE",
            currency_code="USD",
            source_published_at=datetime(2025, 7, 1, tzinfo=UTC),
        ),
    )
    repository = EmptyCalculationRepository(facts)

    MetricCalculationService().calculate_snapshot(SNAPSHOT_ID, repository)

    metric = next(item for item in repository.metrics if item.metric_code == "revenue_ttm")
    assert metric.value == Decimal("120")
    assert metric.metric_period == "TTM:ANNUAL_YTD_BRIDGE"
    assert {item.input_role for item in repository.inputs if item.metric_code == "revenue_ttm"} == {
        "latest_fy",
        "latest_ytd",
        "prior_ytd",
    }
