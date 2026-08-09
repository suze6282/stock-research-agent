"""Deterministic persisted-provider provenance classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from stock_research_agent.domain.data_access.enums import ProviderStatus


@dataclass(frozen=True)
class ProviderEvidenceMarkers:
    data_origin: Literal["FIXTURE", "LIVE", "UNKNOWN"]
    access_mode: Literal["OFFLINE", "ONLINE", "UNKNOWN"]
    live_status: Literal["NOT_LIVE", "LIVE", "UNKNOWN"]
    warnings: tuple[str, ...] = ()


def classify_provider_evidence(
    *,
    provider_type: str,
    status: ProviderStatus,
    terms_status: str,
) -> ProviderEvidenceMarkers:
    """Classify only persisted, explicitly verified provider metadata as Live."""

    if provider_type == "FIXTURE":
        return ProviderEvidenceMarkers("FIXTURE", "OFFLINE", "NOT_LIVE")
    if status is ProviderStatus.APPROVED and terms_status == "VERIFIED":
        return ProviderEvidenceMarkers("LIVE", "ONLINE", "LIVE")
    return ProviderEvidenceMarkers(
        "UNKNOWN",
        "UNKNOWN",
        "UNKNOWN",
        ("PROVIDER_LIVE_STATUS_UNVERIFIED",),
    )


__all__ = ["ProviderEvidenceMarkers", "classify_provider_evidence"]
