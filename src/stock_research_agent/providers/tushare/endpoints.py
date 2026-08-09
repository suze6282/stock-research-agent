"""Blocked production endpoint policy for Tushare."""

from collections.abc import Mapping
from types import MappingProxyType

from stock_research_agent.domain.providers.http import ProviderEndpointPolicy

TUSHARE_PRODUCTION_ENDPOINT_POLICIES: Mapping[str, ProviderEndpointPolicy] = MappingProxyType({})


def resolve_tushare_live_endpoint(endpoint: str) -> ProviderEndpointPolicy:
    """Reject production access until HTTPS, rights, and entitlement are approved."""

    del endpoint
    raise ValueError("TUSHARE_PRODUCTION_ACCESS_BLOCKED")
