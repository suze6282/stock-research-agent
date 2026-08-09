"""Small dependency-free foundations shared by later domain modules."""

from stock_research_agent.domain.common.clock import Clock, SystemClock
from stock_research_agent.domain.common.types import JsonScalar, JsonValue

__all__ = ["Clock", "JsonScalar", "JsonValue", "SystemClock"]
