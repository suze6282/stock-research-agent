"""Exact financial display semantics without recalculation or FX conversion."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from stock_research_agent.domain.financials.enums import QualityStatus
from stock_research_agent.domain.reports.enums import ReportLocale
from stock_research_agent.domain.reports.schemas import (
    FrozenReportContract,
    Version,
)
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    EvidenceStatus,
    EvidenceType,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchClaimRecord,
    ResearchEvidenceRecord,
)


class ReportValueState(StrEnum):
    VALUE = "VALUE"
    ZERO = "ZERO"
    NULL = "NULL"
    NOT_MEANINGFUL = "NOT_MEANINGFUL"
    BLOCKED = "BLOCKED"


class ReportDisplayKind(StrEnum):
    DECIMAL = "DECIMAL"
    PERCENT = "PERCENT"


class ReportPeriodBasis(StrEnum):
    ANNUAL = "ANNUAL"
    QUARTER = "QUARTER"
    INSTANT = "INSTANT"
    TTM_FOUR_QUARTERS = "TTM_FOUR_QUARTERS"
    TTM_ANNUAL_YTD_BRIDGE = "TTM_ANNUAL_YTD_BRIDGE"
    A_SHARE_CUMULATIVE = "A_SHARE_CUMULATIVE"
    A_SHARE_DERIVED_QUARTER = "A_SHARE_DERIVED_QUARTER"


class FiscalCalendarBasis(StrEnum):
    CALENDAR = "CALENDAR"
    NON_CALENDAR = "NON_CALENDAR"
    WEEK_52_53 = "WEEK_52_53"


class ReportNumericValue(FrozenReportContract):
    value: Decimal | None
    value_state: ReportValueState
    unit: str = Field(min_length=1, max_length=32)
    currency_code: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    display_kind: ReportDisplayKind
    period: str = Field(min_length=1, max_length=64)
    period_basis: ReportPeriodBasis
    fiscal_calendar_basis: FiscalCalendarBasis
    quality_status: QualityStatus
    formula_version: Version

    @model_validator(mode="after")
    def require_exact_state_shape(self) -> Self:
        if self.value is not None and not self.value.is_finite():
            raise ValueError("financial display value must be finite")
        if self.value_state is ReportValueState.VALUE:
            if self.value is None or self.value == 0:
                raise ValueError("VALUE requires a non-zero Decimal")
        elif self.value_state is ReportValueState.ZERO:
            if self.value != 0:
                raise ValueError("ZERO requires exact Decimal zero")
        elif self.value is not None:
            raise ValueError("non-numeric states cannot carry a value")
        if (
            self.value_state is ReportValueState.BLOCKED
            and self.quality_status is not QualityStatus.BLOCKED
        ):
            raise ValueError("BLOCKED display requires blocked quality")
        return self


class FormattedValue(FrozenReportContract):
    locale: ReportLocale
    display_value: str = Field(min_length=1, max_length=128)
    exact_value: str | None
    value_state: ReportValueState
    unit: str
    currency_code: str | None
    period: str
    qualifiers: tuple[str, ...] = Field(max_length=10)
    quality_status: QualityStatus
    formula_version: Version


class FinancialDisplayError(ValueError):
    """Stable rejection for a display that drifts from financial lineage."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def format_report_value(
    value: ReportNumericValue,
    locale: ReportLocale,
) -> FormattedValue:
    """Format an exact value without rounding, conversion, or missing-value fill."""

    exact = None if value.value is None else str(value.value)
    if value.value_state is ReportValueState.VALUE:
        assert value.value is not None
        display = (
            f"{value.value * Decimal(100)}%"
            if value.display_kind is ReportDisplayKind.PERCENT
            else str(value.value)
        )
    else:
        display = {
            ReportValueState.ZERO: "ZERO",
            ReportValueState.NULL: "NULL",
            ReportValueState.NOT_MEANINGFUL: "N/M",
            ReportValueState.BLOCKED: "BLOCKED",
        }[value.value_state]
    return FormattedValue(
        locale=locale,
        display_value=display,
        exact_value=exact,
        value_state=value.value_state,
        unit=value.unit,
        currency_code=value.currency_code,
        period=value.period,
        qualifiers=_qualifiers(value),
        quality_status=value.quality_status,
        formula_version=value.formula_version,
    )


def validate_financial_display(
    claim: ResearchClaimRecord,
    evidence: ResearchEvidenceRecord,
) -> None:
    """Require exact Stage 7 Claim/Evidence financial display parity."""

    if evidence.status is not EvidenceStatus.VALID:
        raise FinancialDisplayError("FINANCIAL_EVIDENCE_NOT_VALID")
    if claim.lifecycle_status is not ClaimLifecycleStatus.VALIDATED or claim.support_status is None:
        raise FinancialDisplayError("FINANCIAL_CLAIM_NOT_VALIDATED")
    if claim.run_id != evidence.run_id:
        raise FinancialDisplayError("FINANCIAL_RUN_MISMATCH")
    if claim.as_of_time != evidence.research_as_of_time:
        raise FinancialDisplayError("FINANCIAL_AS_OF_MISMATCH")
    if evidence.source_checksum is None:
        raise FinancialDisplayError("FINANCIAL_SOURCE_CHECKSUM_MISSING")
    payload = evidence.payload
    comparisons = (
        ("value", None if claim.value is None else str(claim.value)),
        ("unit", claim.unit),
        ("currency_code", claim.currency_code),
        ("period", claim.period),
        ("metric_basis", claim.metric_basis),
    )
    for key, expected in comparisons:
        actual = payload.get(key)
        if isinstance(actual, float) or actual != expected:
            raise FinancialDisplayError(f"FINANCIAL_{key.upper()}_MISMATCH")
    if evidence.evidence_type is EvidenceType.DERIVED_METRIC_EVIDENCE and (
        evidence.calculation_run_id is None
        or not evidence.calculation_input_ids
        or evidence.formula_version is None
    ):
        raise FinancialDisplayError("FINANCIAL_CALCULATION_LINEAGE_MISSING")


def _qualifiers(value: ReportNumericValue) -> tuple[str, ...]:
    period = {
        ReportPeriodBasis.ANNUAL: None,
        ReportPeriodBasis.QUARTER: "PERIOD:SINGLE_QUARTER",
        ReportPeriodBasis.INSTANT: "PERIOD:INSTANT",
        ReportPeriodBasis.TTM_FOUR_QUARTERS: "TTM:FOUR_QUARTERS",
        ReportPeriodBasis.TTM_ANNUAL_YTD_BRIDGE: "TTM:ANNUAL_YTD_BRIDGE",
        ReportPeriodBasis.A_SHARE_CUMULATIVE: "A_SHARE:CUMULATIVE_REPORTED",
        ReportPeriodBasis.A_SHARE_DERIVED_QUARTER: "A_SHARE:DERIVED_SINGLE_QUARTER",
    }[value.period_basis]
    calendar = {
        FiscalCalendarBasis.CALENDAR: None,
        FiscalCalendarBasis.NON_CALENDAR: "FISCAL_CALENDAR:NON_CALENDAR",
        FiscalCalendarBasis.WEEK_52_53: "FISCAL_CALENDAR:52_53_WEEK",
    }[value.fiscal_calendar_basis]
    return tuple(item for item in (period, calendar) if item is not None)
