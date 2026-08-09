from __future__ import annotations

from datetime import date
from importlib import import_module

import pytest
from pydantic import ValidationError


def _schemas() -> object:
    return import_module("stock_research_agent.providers.tushare.schemas")


def test_tushare_request_is_exact_bounded_and_has_stable_page_identity() -> None:
    schemas = _schemas()
    request = schemas.TushareOfflineRequest(  # type: ignore[attr-defined]
        endpoint=schemas.TushareEndpoint.DAILY,  # type: ignore[attr-defined]
        ts_code="601138.SH",
        fields=("close", "trade_date", "ts_code"),
        range_start=date(2026, 7, 1),
        range_end=date(2026, 7, 10),
        period=None,
        offset=0,
        limit=100,
    )

    assert request.page_identity == request.page_identity
    assert len(request.page_identity) == 64
    assert "token" not in type(request).model_fields


def test_tushare_response_preserves_exact_strings_and_field_order() -> None:
    schemas = _schemas()
    response = schemas.TushareOfflineResponse(  # type: ignore[attr-defined]
        endpoint=schemas.TushareEndpoint.DAILY,  # type: ignore[attr-defined]
        fields=("close", "trade_date", "ts_code"),
        items=(("66.27", "20260710", "601138.SH"),),
        offset=0,
        has_more=False,
    )

    assert response.items[0][0] == "66.27"
    assert response.fields == ("close", "trade_date", "ts_code")


def test_tushare_record_metadata_keeps_dates_period_and_update_distinct() -> None:
    schemas = _schemas()
    metadata = schemas.TushareRecordMetadata(  # type: ignore[attr-defined]
        endpoint=schemas.TushareEndpoint.INCOME,  # type: ignore[attr-defined]
        ts_code="601138.SH",
        provider_record_id="601138.SH:20251231:1",
        ann_date=date(2026, 3, 20),
        actual_ann_date=None,
        period=date(2025, 12, 31),
        update_flag="1",
        warning_codes=(),
    )

    assert metadata.ann_date != metadata.period
    assert metadata.actual_ann_date is None
    assert metadata.update_flag == "1"


def test_tushare_provider_metric_cannot_be_promoted_to_stage5_formula() -> None:
    schemas = _schemas()
    descriptor = schemas.TushareFieldDescriptor(  # type: ignore[attr-defined]
        endpoint=schemas.TushareEndpoint.FINA_INDICATOR,  # type: ignore[attr-defined]
        field_name="roe",
        field_role=schemas.TushareFieldRole.PROVIDER_METRIC,  # type: ignore[attr-defined]
        canonical_formula_code=None,
    )
    assert descriptor.field_role.value == "PROVIDER_METRIC"

    with pytest.raises(ValidationError):
        schemas.TushareFieldDescriptor(  # type: ignore[attr-defined]
            endpoint=schemas.TushareEndpoint.FINA_INDICATOR,  # type: ignore[attr-defined]
            field_name="roe",
            field_role=schemas.TushareFieldRole.PROVIDER_METRIC,  # type: ignore[attr-defined]
            canonical_formula_code="RETURN_ON_EQUITY",
        )


@pytest.mark.parametrize(
    ("model_name", "changes"),
    (
        ("request", {"endpoint": "daily_basic"}),
        ("request", {"fields": ("ts_code", "ts_code")}),
        ("request", {"ts_code": None}),
        ("response", {"items": ((66.27, "20260710", "601138.SH"),)}),
        (
            "metadata",
            {
                "ann_date": None,
                "actual_ann_date": None,
                "warning_codes": (),
            },
        ),
    ),
)
def test_tushare_contracts_reject_unverified_or_ambiguous_values(
    model_name: str,
    changes: dict[str, object],
) -> None:
    schemas = _schemas()
    if model_name == "request":
        values: dict[str, object] = {
            "endpoint": schemas.TushareEndpoint.DAILY,  # type: ignore[attr-defined]
            "ts_code": "601138.SH",
            "fields": ("close", "trade_date", "ts_code"),
            "range_start": date(2026, 7, 1),
            "range_end": date(2026, 7, 10),
            "period": None,
            "offset": 0,
            "limit": 100,
        }
        model = schemas.TushareOfflineRequest  # type: ignore[attr-defined]
    elif model_name == "response":
        values = {
            "endpoint": schemas.TushareEndpoint.DAILY,  # type: ignore[attr-defined]
            "fields": ("close", "trade_date", "ts_code"),
            "items": (("66.27", "20260710", "601138.SH"),),
            "offset": 0,
            "has_more": False,
        }
        model = schemas.TushareOfflineResponse  # type: ignore[attr-defined]
    else:
        values = {
            "endpoint": schemas.TushareEndpoint.INCOME,  # type: ignore[attr-defined]
            "ts_code": "601138.SH",
            "provider_record_id": "601138.SH:20251231:1",
            "ann_date": date(2026, 3, 20),
            "actual_ann_date": None,
            "period": date(2025, 12, 31),
            "update_flag": "1",
            "warning_codes": (),
        }
        model = schemas.TushareRecordMetadata  # type: ignore[attr-defined]
    values.update(changes)

    with pytest.raises((ValidationError, ValueError)):
        model(**values)
