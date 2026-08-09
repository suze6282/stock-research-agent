"""Clock abstraction without business or infrastructure dependencies."""

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Supply timezone-aware timestamps to code that needs an explicit clock."""

    def now(self) -> datetime:
        """Return the current time."""
        ...


class SystemClock:
    """Production clock using the system's UTC time."""

    def now(self) -> datetime:
        """Return a timezone-aware UTC timestamp."""
        return datetime.now(UTC)
