from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from uuid import UUID

from stock_research_agent.domain.live_evidence.exceptions import LiveEvidenceValidationError
from stock_research_agent.domain.live_evidence.schemas import (
    LiveAuthorizationGrantRecord,
    LiveAuthorizationGrantWrite,
)

type GrantContract = LiveAuthorizationGrantWrite | LiveAuthorizationGrantRecord
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def canonical_grant(value: GrantContract) -> str:
    material = value.model_dump(
        mode="python",
        exclude={"canonical_checksum", "created_at", "id"},
    )
    material["schema"] = "live-authorization-grant-v1"
    return json.dumps(
        _json_value(material),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def grant_checksum(value: GrantContract) -> str:
    return hashlib.sha256(canonical_grant(value).encode("utf-8")).hexdigest()


def verify_grant_checksum(value: GrantContract) -> None:
    if value.canonical_checksum != grant_checksum(value):
        raise LiveEvidenceValidationError("AUTH_CHECKSUM_INVALID")


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")
