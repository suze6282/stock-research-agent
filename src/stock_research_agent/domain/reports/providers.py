"""Future-safe report provider ports with blocked production model adapters."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import Field, model_validator

from stock_research_agent.domain.reports.reflection import CandidateReflectionFinding
from stock_research_agent.domain.reports.reporting import StructuredReportBlock
from stock_research_agent.domain.reports.schemas import (
    Checksum,
    FrozenReportContract,
    ReportInputManifest,
    Version,
)


class ProviderAvailability(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class ProviderClassification(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    MODEL = "MODEL"
    TEST_ONLY = "TEST_ONLY"


class ReportProviderMetadata(FrozenReportContract):
    provider_name: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,63}$")
    provider_version: Version
    classification: ProviderClassification
    production_default: bool
    requires_network: bool
    model_token_budget: int = Field(ge=0, le=0)

    @model_validator(mode="after")
    def prevent_model_or_test_default(self) -> ReportProviderMetadata:
        if (
            self.production_default
            and self.classification is not ProviderClassification.DETERMINISTIC
        ):
            raise ValueError("only deterministic providers may be production defaults")
        return self


class ProviderHealth(FrozenReportContract):
    status: ProviderAvailability
    reason_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_:-]{0,127}$",
    )
    consumed_model_tokens: int = Field(ge=0, le=0)

    @model_validator(mode="after")
    def require_blocked_reason(self) -> ProviderHealth:
        if (self.status is ProviderAvailability.BLOCKED) != (self.reason_code is not None):
            raise ValueError("blocked health requires one stable reason")
        return self


class ReportRenderContext(FrozenReportContract):
    manifest: ReportInputManifest
    request_checksum: Checksum
    claim_ids: tuple[UUID, ...]


class ReportReflectionContext(FrozenReportContract):
    manifest: ReportInputManifest
    research_report_id: UUID
    report_checksum: Checksum
    round_number: int = Field(ge=1, le=2)


class CandidateReportBlock(FrozenReportContract):
    block: StructuredReportBlock
    claim_ids: tuple[UUID, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def require_exact_claim_declaration(self) -> CandidateReportBlock:
        if self.claim_ids != tuple(sorted(set(self.claim_ids), key=str)):
            raise ValueError("candidate claim ids must be sorted and unique")
        payload_claim = self.block.payload.get("claim_id")
        if payload_claim is None or UUID(str(payload_claim)) not in self.claim_ids:
            raise ValueError("candidate block must declare its payload claim")
        return self


class ReportProviderBlockedError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@runtime_checkable
class NarrativeProvider(Protocol):
    @property
    def metadata(self) -> ReportProviderMetadata: ...

    def validate_configuration(self) -> ProviderHealth: ...

    def render_candidate_blocks(
        self,
        context: ReportRenderContext,
    ) -> tuple[CandidateReportBlock, ...]: ...


@runtime_checkable
class ReflectionProvider(Protocol):
    @property
    def metadata(self) -> ReportProviderMetadata: ...

    def validate_configuration(self) -> ProviderHealth: ...

    def propose_findings(
        self,
        context: ReportReflectionContext,
    ) -> tuple[CandidateReflectionFinding, ...]: ...


class BlockedModelNarrativeProvider:
    @property
    def metadata(self) -> ReportProviderMetadata:
        return _blocked_model_metadata("blocked-model-narrative")

    def validate_configuration(self) -> ProviderHealth:
        return _blocked_health("MODEL_NARRATIVE_PROVIDER_NOT_CONFIGURED")

    def render_candidate_blocks(
        self,
        context: ReportRenderContext,
    ) -> tuple[CandidateReportBlock, ...]:
        del context
        raise ReportProviderBlockedError("MODEL_NARRATIVE_PROVIDER_BLOCKED")


class BlockedModelReflectionProvider:
    @property
    def metadata(self) -> ReportProviderMetadata:
        return _blocked_model_metadata("blocked-model-reflection")

    def validate_configuration(self) -> ProviderHealth:
        return _blocked_health("MODEL_REFLECTION_PROVIDER_NOT_CONFIGURED")

    def propose_findings(
        self,
        context: ReportReflectionContext,
    ) -> tuple[CandidateReflectionFinding, ...]:
        del context
        raise ReportProviderBlockedError("MODEL_REFLECTION_PROVIDER_BLOCKED")


def _blocked_model_metadata(name: str) -> ReportProviderMetadata:
    return ReportProviderMetadata(
        provider_name=name,
        provider_version="blocked-report-provider-v1",
        classification=ProviderClassification.MODEL,
        production_default=False,
        requires_network=False,
        model_token_budget=0,
    )


def _blocked_health(reason: str) -> ProviderHealth:
    return ProviderHealth(
        status=ProviderAvailability.BLOCKED,
        reason_code=reason,
        consumed_model_tokens=0,
    )


__all__ = [
    "BlockedModelNarrativeProvider",
    "BlockedModelReflectionProvider",
    "CandidateReportBlock",
    "NarrativeProvider",
    "ProviderAvailability",
    "ProviderClassification",
    "ProviderHealth",
    "ReflectionProvider",
    "ReportProviderBlockedError",
    "ReportProviderMetadata",
    "ReportReflectionContext",
    "ReportRenderContext",
]
