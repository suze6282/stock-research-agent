from __future__ import annotations

import json

import pytest

from stock_research_agent.domain.live_evidence.enums import ManualValidationStatus
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)
from stock_research_agent.domain.live_evidence.json_security import (
    JsonSafetyPolicy,
    load_bounded_json,
)


def _nested_array(depth: int) -> bytes:
    value: object = 1
    for _index in range(depth):
        value = [value]
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def test_depth_limit_accepts_exact_boundary() -> None:
    result = load_bounded_json(_nested_array(32), JsonSafetyPolicy(max_depth=32))

    assert result.status is ManualValidationStatus.PASS
    assert result.max_depth == 32


def test_depth_limit_rejects_one_level_over_boundary() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        load_bounded_json(_nested_array(33), JsonSafetyPolicy(max_depth=32))

    assert exc_info.value.code == "JSON_DEPTH_EXCEEDED"


@pytest.mark.parametrize(
    "content",
    [b"\xff\xfe{}", b'{"unterminated":', b"123", b'"scalar"'],
)
def test_invalid_encoding_structure_or_scalar_root_is_rejected(content: bytes) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        load_bounded_json(content, JsonSafetyPolicy())

    assert exc_info.value.code == "JSON_ENCODING_INVALID"


def test_utf8_bom_is_accepted_deterministically() -> None:
    result = load_bounded_json(b'\xef\xbb\xbf{"synthetic":true}', JsonSafetyPolicy())

    assert result.status is ManualValidationStatus.PASS
    assert result.node_count == 2


def test_node_limit_is_enforced() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        load_bounded_json(b'{"items":[1,2]}', JsonSafetyPolicy(max_nodes=3))

    assert exc_info.value.code == "JSON_NODE_LIMIT_EXCEEDED"


def test_string_limit_applies_to_keys_and_values() -> None:
    for content in (b'{"long_key":1}', b'{"key":"long_value"}'):
        with pytest.raises(LiveEvidenceValidationError) as exc_info:
            load_bounded_json(content, JsonSafetyPolicy(max_string_characters=4))
        assert exc_info.value.code == "JSON_STRING_LIMIT_EXCEEDED"


def test_array_limit_is_enforced() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        load_bounded_json(b"[1,2,3]", JsonSafetyPolicy(max_array_length=2))

    assert exc_info.value.code == "JSON_ARRAY_LIMIT_EXCEEDED"


def test_duplicate_object_key_is_rejected_before_overwrite() -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        load_bounded_json(b'{"same":1,"same":2}', JsonSafetyPolicy())

    assert exc_info.value.code == "JSON_DUPLICATE_KEY"


@pytest.mark.parametrize("constant", [b"NaN", b"Infinity", b"-Infinity"])
def test_nonfinite_number_is_rejected(constant: bytes) -> None:
    with pytest.raises(LiveEvidenceValidationError) as exc_info:
        load_bounded_json(b'{"value":' + constant + b"}", JsonSafetyPolicy())

    assert exc_info.value.code == "JSON_NONFINITE_NUMBER"
