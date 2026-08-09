from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

EXPECTED_JSON = (
    '{"amount":"123.4500","at":"2026-07-23T04:05:06Z",'
    '"id":"12345678-1234-5678-1234-567812345678",'
    '"nested":{"a":true,"z":2},"text":"工业富联"}'
)
EXPECTED_CHECKSUM = "ebee592fe05692aaedbba46af97e90cdcfe11d62920dc53931a8b56e91a5ec57"
MODULE = "stock_research_agent.domain.research_agent.canonical"


def _functions() -> tuple[Callable[[object], str], Callable[[object], str]]:
    assert importlib.util.find_spec(MODULE) is not None
    module = importlib.import_module(MODULE)
    return module.canonical_json, module.stable_checksum


def test_canonical_json_has_independently_fixed_bytes_and_checksum() -> None:
    canonical_json, stable_checksum = _functions()
    value = {
        "text": "工业富联",
        "nested": {"z": 2, "a": True},
        "id": UUID("12345678-1234-5678-1234-567812345678"),
        "at": datetime(2026, 7, 23, 4, 5, 6, tzinfo=UTC),
        "amount": Decimal("123.4500"),
    }

    assert canonical_json(value) == EXPECTED_JSON
    assert stable_checksum(value) == EXPECTED_CHECKSUM


def test_canonical_json_normalizes_timezone_and_sequence_shape() -> None:
    canonical_json, _ = _functions()
    value = {
        "at": datetime(
            2026,
            7,
            23,
            12,
            5,
            6,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        "values": (Decimal("0"), None, False),
    }

    assert canonical_json(value) == ('{"at":"2026-07-23T04:05:06Z","values":["0",null,false]}')


@pytest.mark.parametrize(
    "value",
    [
        {"amount": 1.25},
        {"at": datetime(2026, 7, 23, 4, 5, 6)},
        {1: "non-string-key"},
        {"unsupported": object()},
    ],
)
def test_canonical_json_rejects_ambiguous_or_unsupported_values(value: object) -> None:
    canonical_json, _ = _functions()
    with pytest.raises((TypeError, ValueError)):
        canonical_json(value)
