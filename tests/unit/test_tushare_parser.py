from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID

import pytest

from stock_research_agent.domain.providers.enums import ProviderSyntheticStatus

PROVIDER_ID = UUID("00000000-0000-4000-8000-000000000581")
CAPABILITY_ID = UUID("00000000-0000-4000-8000-000000000582")
ARTIFACT_ID = UUID("00000000-0000-4000-8000-000000000583")
AS_OF = datetime(2026, 7, 29, tzinfo=UTC)


def _module() -> object:
    return import_module("stock_research_agent.providers.tushare.adapter")


def _schemas() -> object:
    return import_module("stock_research_agent.providers.tushare.schemas")


def _body(fields: list[str], items: list[list[object]]) -> bytes:
    return json.dumps(
        {"code": 0, "msg": None, "data": {"fields": fields, "items": items}},
        separators=(",", ":"),
    ).encode()


def _context(body: bytes, **changes: object) -> object:
    module = _module()
    schemas = _schemas()
    values: dict[str, object] = {
        "provider_definition_id": PROVIDER_ID,
        "provider_capability_id": CAPABILITY_ID,
        "raw_artifact_id": ARTIFACT_ID,
        "source_checksum": hashlib.sha256(body).hexdigest(),
        "manifest_checksum": "b" * 64,
        "source_identity": "TUSHARE_FIXTURE:daily:601138.SH",
        "endpoint": schemas.TushareEndpoint.DAILY,  # type: ignore[attr-defined]
        "provider_security_identifier": "601138.SH",
        "numeric_fields": ("close",),
        "provider_metric_fields": (),
        "publication_fields": (),
        "period_field": "trade_date",
        "source_published_at": None,
        "research_as_of_time": AS_OF,
        "synthetic_status": ProviderSyntheticStatus.SYNTHETIC_TEST_ONLY,
    }
    values.update(changes)
    return module.TushareParseContext(**values)  # type: ignore[attr-defined]


def test_tushare_daily_parser_preserves_decimal_missing_and_raw_lineage() -> None:
    body = _body(
        ["close", "trade_date", "ts_code"],
        [["66.2700", "20260710", "601138.SH"], [None, "20260711", "601138.SH"]],
    )

    batch = _module().TushareAdapter().parse_response(body, _context(body))  # type: ignore[attr-defined]

    assert batch.record_count == 2
    assert batch.records[0].source_checksum == hashlib.sha256(body).hexdigest()
    assert batch.records[0].numeric_values["close"] == "66.2700"
    assert batch.records[1].numeric_values["close"] is None
    assert batch.records[1].numeric_values["close"] != "0"
    assert all(record.source_published_at is None for record in batch.records)
    assert all(record.warning_codes == ("UNKNOWN_PUBLISHED_AT",) for record in batch.records)


def test_tushare_statement_remains_provider_reported_cumulative_without_ttm() -> None:
    schemas = _schemas()
    body = _body(
        ["ann_date", "end_date", "revenue", "ts_code", "update_flag"],
        [["20260430", "20260331", "100.00", "601138.SH", "1"]],
    )
    context = _context(
        body,
        endpoint=schemas.TushareEndpoint.INCOME,  # type: ignore[attr-defined]
        source_identity="TUSHARE_FIXTURE:income:601138.SH",
        numeric_fields=("revenue",),
        publication_fields=("ann_date",),
        period_field="end_date",
    )

    record = _module().TushareAdapter().parse_response(body, context).records[0]  # type: ignore[attr-defined]

    assert record.numeric_values == {"revenue": "100.00"}
    assert record.text_values["aggregation_semantics"] == "PROVIDER_REPORTED_UNNORMALIZED"
    assert "ttm" not in record.numeric_values
    assert "quarter_value" not in record.numeric_values
    assert "formula_code" not in record.text_values


def test_tushare_provider_metric_keeps_provider_provenance_not_formula() -> None:
    schemas = _schemas()
    body = _body(
        ["ann_date", "end_date", "roe", "ts_code", "update_flag"],
        [["20260430", "20260331", "12.3400", "601138.SH", "1"]],
    )
    context = _context(
        body,
        endpoint=schemas.TushareEndpoint.FINA_INDICATOR,  # type: ignore[attr-defined]
        source_identity="TUSHARE_FIXTURE:fina_indicator:601138.SH",
        numeric_fields=("roe",),
        provider_metric_fields=("roe",),
        publication_fields=("ann_date",),
        period_field="end_date",
    )

    record = _module().TushareAdapter().parse_response(body, context).records[0]  # type: ignore[attr-defined]

    assert record.text_values["provider_metric_fields"] == "roe"
    assert "canonical_formula_code" not in record.text_values


@pytest.mark.parametrize(
    "body",
    (
        b"{bad-json",
        _body(["close", "ts_code"], [[66.27, "601138.SH"]]),
        _body(["close", "close", "ts_code"], [["1", "1", "601138.SH"]]),
        _body(["close", "ts_code"], [["1", "000001.SZ"]]),
    ),
)
def test_tushare_parser_rejects_malformed_float_duplicate_or_wrong_identity(
    body: bytes,
) -> None:
    with pytest.raises(ValueError):
        _module().TushareAdapter().parse_response(body, _context(body))  # type: ignore[attr-defined]


def test_tushare_parser_rejects_checksum_future_and_raw_projection() -> None:
    body = _body(
        ["close", "trade_date", "ts_code"],
        [["66.27", "20260710", "601138.SH"]],
    )
    with pytest.raises(ValueError, match="CHECKSUM"):
        _module().TushareAdapter().parse_response(  # type: ignore[attr-defined]
            body, _context(body, source_checksum="a" * 64)
        )
    with pytest.raises(ValueError, match="FUTURE"):
        _module().TushareAdapter().parse_response(  # type: ignore[attr-defined]
            body,
            _context(
                body,
                source_published_at=datetime(2026, 7, 30, tzinfo=UTC),
            ),
        )
    record = _module().TushareAdapter().parse_response(body, _context(body)).records[0]  # type: ignore[attr-defined]
    assert body.decode() not in record.text_values.values()
