"""Deterministic bounded JSON loading for offline manual evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass

from stock_research_agent.domain.live_evidence.enums import ManualValidationStatus
from stock_research_agent.domain.live_evidence.exceptions import (
    LiveEvidenceValidationError,
)


@dataclass(frozen=True, slots=True)
class JsonSafetyPolicy:
    max_depth: int = 32
    max_nodes: int = 100_000
    max_string_characters: int = 1_000_000
    max_array_length: int = 100_000


@dataclass(frozen=True, slots=True)
class JsonSafetyResult:
    status: ManualValidationStatus
    value: object
    node_count: int
    max_depth: int


def load_bounded_json(content: bytes, policy: JsonSafetyPolicy) -> JsonSafetyResult:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise LiveEvidenceValidationError("JSON_DUPLICATE_KEY")
            result[key] = item
        return result

    def reject_nonfinite(_value: str) -> object:
        raise LiveEvidenceValidationError("JSON_NONFINITE_NUMBER")

    try:
        decoded = content.decode("utf-8-sig", errors="strict")
        value = json.loads(
            decoded,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LiveEvidenceValidationError("JSON_ENCODING_INVALID") from error
    if not isinstance(value, (dict, list)):
        raise LiveEvidenceValidationError("JSON_ENCODING_INVALID")

    node_count = 0
    observed_depth = 0

    def walk(item: object, container_depth: int) -> None:
        nonlocal node_count, observed_depth
        node_count += 1
        if node_count > policy.max_nodes:
            raise LiveEvidenceValidationError("JSON_NODE_LIMIT_EXCEEDED")
        if isinstance(item, dict):
            depth = container_depth + 1
            if depth > policy.max_depth:
                raise LiveEvidenceValidationError("JSON_DEPTH_EXCEEDED")
            observed_depth = max(observed_depth, depth)
            for key, child in item.items():
                if len(key) > policy.max_string_characters:
                    raise LiveEvidenceValidationError("JSON_STRING_LIMIT_EXCEEDED")
                walk(child, depth)
        elif isinstance(item, list):
            depth = container_depth + 1
            if depth > policy.max_depth:
                raise LiveEvidenceValidationError("JSON_DEPTH_EXCEEDED")
            if len(item) > policy.max_array_length:
                raise LiveEvidenceValidationError("JSON_ARRAY_LIMIT_EXCEEDED")
            observed_depth = max(observed_depth, depth)
            for child in item:
                walk(child, depth)
        elif isinstance(item, str) and len(item) > policy.max_string_characters:
            raise LiveEvidenceValidationError("JSON_STRING_LIMIT_EXCEEDED")

    walk(value, 0)
    return JsonSafetyResult(
        status=ManualValidationStatus.PASS,
        value=value,
        node_count=node_count,
        max_depth=observed_depth,
    )
