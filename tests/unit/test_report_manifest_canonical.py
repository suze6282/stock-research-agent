from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent.enums import ResearchType

EXPECTED_JSON = (
    '{"amount":"123.4500","at":"2026-07-26T01:02:03Z",'
    '"id":"12345678-1234-5678-1234-567812345678",'
    '"mode":"FULL_RESEARCH_PACKAGE","text":"MU"}'
)
EXPECTED_CHECKSUM = "0e6ec4a2baa8307f8cd0e3fa607b9b81b02c47710e1d6763bde979b57d261211"


def _functions() -> SimpleNamespace:
    try:
        module = import_module("stock_research_agent.domain.reports.canonical")
    except ModuleNotFoundError:
        pytest.fail("Stage 8 canonical report serializer is missing")
    return SimpleNamespace(
        canonical_report_json=module.canonical_report_json,
        report_checksum=module.report_checksum,
    )


def test_canonical_report_json_matches_independent_golden_bytes_and_hash() -> None:
    functions = _functions()
    value = {
        "text": "ＭＵ",
        "mode": ResearchType.FULL_RESEARCH_PACKAGE,
        "id": UUID("12345678-1234-5678-1234-567812345678"),
        "at": datetime(2026, 7, 26, 1, 2, 3, tzinfo=UTC),
        "amount": Decimal("123.4500"),
    }

    assert functions.canonical_report_json(value) == EXPECTED_JSON
    assert functions.report_checksum(value) == EXPECTED_CHECKSUM


def test_canonical_report_json_normalizes_keys_text_timezone_and_tuple_shape() -> None:
    functions = _functions()
    value = {
        "Ｂ": "ｅｖｉｄｅｎｃｅ",
        "A": (
            datetime(
                2026,
                7,
                26,
                9,
                2,
                3,
                tzinfo=timezone(timedelta(hours=8)),
            ),
            "e\u0301",
        ),
    }

    assert functions.canonical_report_json(value) == (
        '{"A":["2026-07-26T01:02:03Z","é"],"B":"evidence"}'
    )


def test_canonical_report_json_preserves_explicit_sequence_order() -> None:
    functions = _functions()

    assert functions.canonical_report_json({"values": ("z", "a", "z")}) == (
        '{"values":["z","a","z"]}'
    )


def test_canonical_report_json_is_independent_of_mapping_insertion_order() -> None:
    functions = _functions()
    left = {"z": 2, "a": {"y": False, "x": None}}
    right = {"a": {"x": None, "y": False}, "z": 2}

    assert functions.canonical_report_json(left) == functions.canonical_report_json(right)
    assert functions.report_checksum(left) == functions.report_checksum(right)


@pytest.mark.parametrize(
    "value",
    [
        {"amount": 1.25},
        {"amount": Decimal("NaN")},
        {"at": datetime(2026, 7, 26, 1, 2, 3)},
        {"set": {"a", "b"}},
        {1: "non-string-key"},
        {"unsupported": object()},
        {"bytes": b"not-text"},
    ],
)
def test_canonical_report_json_rejects_ambiguous_or_unsupported_values(
    value: object,
) -> None:
    functions = _functions()

    with pytest.raises((TypeError, ValueError)):
        functions.canonical_report_json(value)


def test_canonical_report_json_rejects_nfkc_key_collisions() -> None:
    functions = _functions()

    with pytest.raises(ValueError, match="normalized mapping keys must be unique"):
        functions.canonical_report_json({"A": 1, "Ａ": 2})


def test_serializer_contract_uses_explicit_callable_signatures() -> None:
    functions = _functions()

    assert isinstance(functions.canonical_report_json, Callable)
    assert isinstance(functions.report_checksum, Callable)
