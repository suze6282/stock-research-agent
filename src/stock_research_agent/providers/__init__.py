"""Data-provider adapter contracts and registry."""

from stock_research_agent.providers.base import DataProviderAdapter
from stock_research_agent.providers.registry import ProviderRegistry

__all__ = ["DataProviderAdapter", "ProviderRegistry"]
