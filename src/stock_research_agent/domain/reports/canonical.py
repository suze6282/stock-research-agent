"""Canonical JSON and checksum primitives for immutable report artifacts."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


def canonical_report_json(value: object) -> str:
    """Encode an explicitly supported value as deterministic UTF-8 JSON text."""

    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def report_checksum(value: object) -> str:
    """Return SHA-256 over canonical report JSON encoded as UTF-8."""

    return hashlib.sha256(canonical_report_json(value).encode("utf-8")).hexdigest()


def _normalize(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        return _normalize(value.value)
    if isinstance(value, str):
        return unicodedata.normalize("NFKC", value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise TypeError("binary floating-point values are not canonical")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Decimal values must be finite")
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime values must include a timezone")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return _normalize_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def _normalize_mapping(value: Mapping[object, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("canonical mapping keys must be strings")
        normalized_key = unicodedata.normalize("NFKC", key)
        if normalized_key in normalized:
            raise ValueError("normalized mapping keys must be unique")
        normalized[normalized_key] = _normalize(item)
    return normalized
