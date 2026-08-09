from __future__ import annotations

from datetime import date
from uuid import UUID

from stock_research_agent.domain.financials.enums import QualityStatus
from stock_research_agent.domain.financials.queries import FinancialQueryService
from stock_research_agent.domain.financials.schemas import DerivedMetricRecord
from stock_research_agent.tools.registry import (
    create_financial_tool_registry,
    create_tool_metadata_registry,
)
from stock_research_agent.tools.schemas import FinancialMetricsEnvelope

SECURITY_ID = UUID("40000000-0000-0000-0000-000000000001")
SNAPSHOT_ID = UUID("90000000-0000-0000-0000-000000000001")
RUN_ID = UUID("a0000000-0000-0000-0000-000000000001")


class MetricReadRepository:
    def read_snapshot_provenance(self, snapshot_id: UUID) -> tuple[str, str, str]:
        assert snapshot_id == SNAPSHOT_ID
        return ("FIXTURE", "OFFLINE", "NOT_LIVE")

    def read_financial_metrics(
        self,
        security_id: UUID,
        snapshot_id: UUID,
        metric_code: str | None,
        limit: int,
    ) -> tuple[DerivedMetricRecord, ...]:
        assert (security_id, snapshot_id, limit) == (SECURITY_ID, SNAPSHOT_ID, 100)
        return (
            DerivedMetricRecord(
                id=UUID("a2000000-0000-0000-0000-000000000001"),
                calculation_run_id=RUN_ID,
                security_id=SECURITY_ID,
                snapshot_id=SNAPSHOT_ID,
                metric_code=metric_code or "gross_margin",
                metric_period="FY",
                period_end=date(2025, 12, 31),
                value=None,
                value_state="NULL",
                unit="RATIO",
                currency_code=None,
                quality_status=QualityStatus.BLOCKED,
                formula_version="1.0.0",
                warning_codes=("SOURCE_MISSING:cost_of_revenue",),
            ),
        )


def test_stage5_read_only_tools_are_canonical_and_never_write_or_network() -> None:
    expected = {
        "get_normalized_financial_facts",
        "get_financial_periods",
        "get_financial_metrics",
        "get_metric_detail",
        "get_metric_lineage",
        "get_calculation_run",
    }
    registry = create_tool_metadata_registry()
    metadata = {item.name: item for item in registry.list()}

    assert expected <= metadata.keys()
    for name in expected:
        assert metadata[name].version == "1.0.0"
        assert metadata[name].read_only is True
        assert metadata[name].writes is False
        assert metadata[name].requires_network is False


def test_financial_metrics_tool_preserves_blocked_null_and_stable_envelope() -> None:
    service = FinancialQueryService(MetricReadRepository())  # type: ignore[arg-type]
    result = create_financial_tool_registry(service).execute(
        "get_financial_metrics",
        "1.0.0",
        {
            "security_id": SECURITY_ID,
            "snapshot_id": SNAPSHOT_ID,
            "metric_code": "gross_margin",
        },
    )

    assert isinstance(result, FinancialMetricsEnvelope)
    assert result.status == "BLOCKED"
    assert result.calculation_run_id == RUN_ID
    assert result.formula_version == "1.0.0"
    assert result.data[0].value is None
    assert result.data[0].value_state == "NULL"
    assert "SOURCE_MISSING:cost_of_revenue" in result.warnings
    assert result.provenance.model_dump() == {
        "data_origin": "FIXTURE",
        "access_mode": "OFFLINE",
        "live_status": "NOT_LIVE",
    }
