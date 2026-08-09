from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from importlib import import_module
from uuid import UUID

import pytest
from pydantic import ValidationError

from stock_research_agent.domain.financials.enums import QualityStatus
from stock_research_agent.domain.reports.enums import ReportLocale
from stock_research_agent.domain.research_agent.enums import (
    ClaimLifecycleStatus,
    ClaimSupportStatus,
    ClaimType,
    EvidenceStatus,
    EvidenceType,
    SyntheticStatus,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchClaimRecord,
    ResearchEvidenceRecord,
)

NOW = datetime(2026, 7, 27, 8, tzinfo=UTC)


def _module() -> object:
    try:
        return import_module("stock_research_agent.domain.reports.formatting")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 financial display formatting is missing")


def _value(**updates: object) -> object:
    module = _module()
    values: dict[str, object] = {
        "value": Decimal("128.4200"),
        "value_state": module.ReportValueState.VALUE,
        "unit": "MONETARY_AMOUNT",
        "currency_code": "CNY",
        "display_kind": module.ReportDisplayKind.DECIMAL,
        "period": "FY2025",
        "period_basis": module.ReportPeriodBasis.ANNUAL,
        "fiscal_calendar_basis": module.FiscalCalendarBasis.CALENDAR,
        "quality_status": QualityStatus.PASS,
        "formula_version": "metric-v1",
    }
    values.update(updates)
    return module.ReportNumericValue.model_validate(values)


def _claim(**updates: object) -> ResearchClaimRecord:
    values: dict[str, object] = {
        "id": UUID(int=1),
        "run_id": UUID(int=2),
        "claim_type": ClaimType.FINANCIAL_METRIC,
        "lifecycle_status": ClaimLifecycleStatus.VALIDATED,
        "support_status": ClaimSupportStatus.SUPPORTED,
        "statement_code": "RETURN_ON_EQUITY",
        "value": Decimal("0.1250"),
        "unit": "RATIO",
        "currency_code": None,
        "period": "TTM",
        "as_of_time": NOW,
        "metric_basis": "TTM:FOUR_QUARTERS",
        "builder_version": "deterministic-claim-builder-v1",
        "validator_version": "claim-support-validator-v1",
        "created_at": NOW,
        "completed_at": NOW,
    }
    values.update(updates)
    return ResearchClaimRecord.model_validate(values)


def _evidence(**updates: object) -> ResearchEvidenceRecord:
    values: dict[str, object] = {
        "id": UUID(int=3),
        "run_id": UUID(int=2),
        "observation_id": UUID(int=4),
        "evidence_type": EvidenceType.DERIVED_METRIC_EVIDENCE,
        "status": EvidenceStatus.VALID,
        "schema_version": "evidence-v1",
        "security_id": UUID(int=5),
        "snapshot_id": UUID(int=6),
        "research_as_of_time": NOW,
        "source_record_type": "derived_metric",
        "source_record_id": UUID(int=7),
        "source_checksum": "a" * 64,
        "published_at": NOW,
        "calculation_run_id": UUID(int=8),
        "calculation_input_ids": (UUID(int=9),),
        "formula_version": "roe-v1",
        "synthetic_status": SyntheticStatus.REAL_VERIFIED,
        "payload": {
            "value": "0.1250",
            "unit": "RATIO",
            "currency_code": None,
            "period": "TTM",
            "metric_basis": "TTM:FOUR_QUARTERS",
        },
        "warning_codes": (),
        "created_at": NOW,
    }
    values.update(updates)
    return ResearchEvidenceRecord.model_validate(values)


def test_decimal_and_percent_formatting_preserve_source_precision() -> None:
    module = _module()
    decimal_value = module.format_report_value(_value(), ReportLocale.EN_US)
    percent_value = module.format_report_value(
        _value(
            value=Decimal("0.1250"),
            unit="RATIO",
            currency_code=None,
            display_kind=module.ReportDisplayKind.PERCENT,
        ),
        ReportLocale.ZH_CN,
    )

    assert decimal_value.display_value == "128.4200"
    assert decimal_value.currency_code == "CNY"
    assert percent_value.display_value == "12.5000%"
    assert percent_value.exact_value == "0.1250"


def test_currency_is_never_converted_or_relabelled() -> None:
    module = _module()
    cny = module.format_report_value(_value(currency_code="CNY"), ReportLocale.ZH_CN)
    usd = module.format_report_value(
        _value(currency_code="USD", value=Decimal("128.4200")),
        ReportLocale.EN_US,
    )

    assert cny.currency_code == "CNY"
    assert usd.currency_code == "USD"
    assert cny.display_value == usd.display_value == "128.4200"
    assert not hasattr(cny, "converted_value")
    assert not hasattr(usd, "fx_rate")


@pytest.mark.parametrize(
    ("state", "value", "quality", "expected"),
    [
        ("ZERO", Decimal("0"), QualityStatus.PASS, "ZERO"),
        ("NULL", None, QualityStatus.PARTIAL, "NULL"),
        ("NOT_MEANINGFUL", None, QualityStatus.PASS, "N/M"),
        ("BLOCKED", None, QualityStatus.BLOCKED, "BLOCKED"),
    ],
)
def test_zero_null_not_meaningful_and_blocked_are_distinct(
    state: str,
    value: Decimal | None,
    quality: QualityStatus,
    expected: str,
) -> None:
    module = _module()
    formatted = module.format_report_value(
        _value(
            value_state=module.ReportValueState(state),
            value=value,
            quality_status=quality,
        ),
        ReportLocale.EN_US,
    )

    assert formatted.display_value == expected
    assert formatted.value_state.value == state


def test_invalid_value_state_shapes_and_binary_float_are_rejected() -> None:
    module = _module()
    with pytest.raises(ValidationError):
        _value(value_state=module.ReportValueState.NULL, value=Decimal("0"))
    with pytest.raises(ValidationError):
        _value(value_state=module.ReportValueState.ZERO, value=None)
    with pytest.raises(ValidationError):
        _value(value=0.1)


@pytest.mark.parametrize(
    ("period_basis", "calendar_basis", "expected"),
    [
        ("TTM_FOUR_QUARTERS", "CALENDAR", "TTM:FOUR_QUARTERS"),
        ("TTM_ANNUAL_YTD_BRIDGE", "NON_CALENDAR", "TTM:ANNUAL_YTD_BRIDGE"),
        ("A_SHARE_CUMULATIVE", "CALENDAR", "A_SHARE:CUMULATIVE_REPORTED"),
        ("A_SHARE_DERIVED_QUARTER", "CALENDAR", "A_SHARE:DERIVED_SINGLE_QUARTER"),
        ("ANNUAL", "WEEK_52_53", "FISCAL_CALENDAR:52_53_WEEK"),
        ("ANNUAL", "NON_CALENDAR", "FISCAL_CALENDAR:NON_CALENDAR"),
    ],
)
def test_period_and_fiscal_basis_remain_explicit(
    period_basis: str,
    calendar_basis: str,
    expected: str,
) -> None:
    module = _module()
    formatted = module.format_report_value(
        _value(
            period_basis=module.ReportPeriodBasis(period_basis),
            fiscal_calendar_basis=module.FiscalCalendarBasis(calendar_basis),
        ),
        ReportLocale.EN_US,
    )

    assert expected in formatted.qualifiers


def test_financial_display_requires_exact_claim_evidence_lineage() -> None:
    module = _module()

    assert module.validate_financial_display(_claim(), _evidence()) is None
    for evidence in (
        _evidence(payload={**_evidence().payload, "value": "0.1251"}),
        _evidence(payload={**_evidence().payload, "unit": "PERCENT"}),
        _evidence(payload={**_evidence().payload, "period": "FY2025"}),
        _evidence(payload={**_evidence().payload, "metric_basis": "ANNUAL"}),
        _evidence(calculation_run_id=None),
        _evidence(calculation_input_ids=()),
    ):
        with pytest.raises(module.FinancialDisplayError):
            module.validate_financial_display(_claim(), evidence)


def test_financial_display_rejects_missing_as_of_or_nonvalid_evidence() -> None:
    module = _module()
    with pytest.raises(module.FinancialDisplayError) as raised:
        module.validate_financial_display(
            _claim(),
            _evidence(status=EvidenceStatus.BLOCKED),
        )
    assert raised.value.code == "FINANCIAL_EVIDENCE_NOT_VALID"

    with pytest.raises(module.FinancialDisplayError) as raised:
        module.validate_financial_display(
            _claim(as_of_time=NOW),
            _evidence(research_as_of_time=datetime(2026, 7, 27, 7, tzinfo=UTC)),
        )
    assert raised.value.code == "FINANCIAL_AS_OF_MISMATCH"
