from __future__ import annotations

from dataclasses import dataclass

from stock_research_agent.domain.reports.providers import (
    CandidateReportBlock,
    ProviderAvailability,
    ProviderClassification,
    ProviderHealth,
    ReportProviderMetadata,
    ReportReflectionContext,
    ReportRenderContext,
)
from stock_research_agent.domain.reports.reflection import CandidateReflectionFinding


@dataclass(frozen=True, slots=True)
class ScriptedTestNarrativeProvider:
    blocks: tuple[CandidateReportBlock, ...]

    @property
    def metadata(self) -> ReportProviderMetadata:
        return _metadata("scripted-test-narrative")

    def validate_configuration(self) -> ProviderHealth:
        return _ready()

    def render_candidate_blocks(
        self,
        context: ReportRenderContext,
    ) -> tuple[CandidateReportBlock, ...]:
        del context
        return self.blocks


@dataclass(frozen=True, slots=True)
class ScriptedTestReflectionProvider:
    findings: tuple[CandidateReflectionFinding, ...]

    @property
    def metadata(self) -> ReportProviderMetadata:
        return _metadata("scripted-test-reflection")

    def validate_configuration(self) -> ProviderHealth:
        return _ready()

    def propose_findings(
        self,
        context: ReportReflectionContext,
    ) -> tuple[CandidateReflectionFinding, ...]:
        del context
        return self.findings


def _metadata(name: str) -> ReportProviderMetadata:
    return ReportProviderMetadata(
        provider_name=name,
        provider_version="scripted-test-provider-v1",
        classification=ProviderClassification.TEST_ONLY,
        production_default=False,
        requires_network=False,
        model_token_budget=0,
    )


def _ready() -> ProviderHealth:
    return ProviderHealth(
        status=ProviderAvailability.READY,
        consumed_model_tokens=0,
    )
