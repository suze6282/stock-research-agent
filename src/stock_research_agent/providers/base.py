"""Protocol implemented by injected data-provider adapters."""

from __future__ import annotations

from typing import Protocol

from stock_research_agent.domain.data_access.enums import ProviderCapability
from stock_research_agent.domain.data_access.schemas import (
    ProviderDescriptor,
    ProviderEnvelope,
    ProviderRequest,
)


class DataProviderAdapter(Protocol):
    code: str
    version: str
    capabilities: frozenset[ProviderCapability]
    descriptor: ProviderDescriptor

    def fetch(self, request: ProviderRequest) -> ProviderEnvelope: ...
