"""Shared strict datetime parsing for CLI presentation boundaries."""

from __future__ import annotations

from datetime import UTC, datetime


def parse_aware_datetime(value: str) -> datetime:
    """Parse an ISO-8601 datetime, require an offset, and normalize to UTC."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid aware ISO datetime") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("invalid aware ISO datetime")
    return parsed.astimezone(UTC)
