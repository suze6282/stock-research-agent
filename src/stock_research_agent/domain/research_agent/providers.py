"""Production-safe provider ports and deterministic compositions."""

from __future__ import annotations

from typing import Protocol

from stock_research_agent.domain.research_agent.enums import (
    PlannerType,
    ProviderHealthStatus,
    ReasoningProviderType,
)
from stock_research_agent.domain.research_agent.planning import (
    DeterministicTemplatePlanner,
)
from stock_research_agent.domain.research_agent.schemas import (
    EvidenceLedgerView,
    PlannerProviderMetadata,
    ProviderHealth,
    ReasoningProviderMetadata,
    ResearchClaimDraft,
    ResearchPlanDraft,
    ResearchPolicyRecord,
    ResearchRequestRecord,
)
from stock_research_agent.domain.research_agent.tool_catalog import ToolCatalogSnapshot


class PlannerProvider(Protocol):
    @property
    def metadata(self) -> PlannerProviderMetadata: ...

    def validate_configuration(self) -> ProviderHealth: ...

    def create_plan(
        self,
        request: ResearchRequestRecord,
        policy: ResearchPolicyRecord,
        tool_catalog: ToolCatalogSnapshot,
    ) -> ResearchPlanDraft: ...


class ReasoningProvider(Protocol):
    @property
    def metadata(self) -> ReasoningProviderMetadata: ...

    def validate_configuration(self) -> ProviderHealth: ...

    def propose_claims(
        self,
        evidence: EvidenceLedgerView,
        policy: ResearchPolicyRecord,
    ) -> tuple[ResearchClaimDraft, ...]: ...


class ProviderUnavailableError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DeterministicPlannerProvider:
    metadata = PlannerProviderMetadata(
        provider_name="deterministic-template-planner",
        provider_version="deterministic-template-v1",
        provider_type=PlannerType.DETERMINISTIC_TEMPLATE,
        test_only=False,
        requires_network=False,
        uses_model=False,
    )

    def __init__(self) -> None:
        self._planner = DeterministicTemplatePlanner()

    def validate_configuration(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderHealthStatus.READY, code="PROVIDER_READY")

    def create_plan(
        self,
        request: ResearchRequestRecord,
        policy: ResearchPolicyRecord,
        tool_catalog: ToolCatalogSnapshot,
    ) -> ResearchPlanDraft:
        return self._planner.create_plan(request, policy, tool_catalog)


class DeterministicReasoningProvider:
    metadata = ReasoningProviderMetadata(
        provider_name="deterministic-claim-builder",
        provider_version="deterministic-claim-builder-v1",
        provider_type=ReasoningProviderType.DETERMINISTIC_RULES,
        test_only=False,
        requires_network=False,
        uses_model=False,
    )

    def validate_configuration(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderHealthStatus.READY, code="PROVIDER_READY")

    def propose_claims(
        self,
        evidence: EvidenceLedgerView,
        policy: ResearchPolicyRecord,
    ) -> tuple[ResearchClaimDraft, ...]:
        return ()


class BlockedModelPlannerProvider:
    metadata = PlannerProviderMetadata(
        provider_name="unconfigured-model-planner",
        provider_version="model-planner-v1",
        provider_type=PlannerType.MODEL_PROVIDER,
        test_only=False,
        requires_network=False,
        uses_model=True,
    )

    def validate_configuration(self) -> ProviderHealth:
        return ProviderHealth(
            status=ProviderHealthStatus.BLOCKED,
            code="MODEL_PROVIDER_NOT_CONFIGURED",
        )

    def create_plan(
        self,
        request: ResearchRequestRecord,
        policy: ResearchPolicyRecord,
        tool_catalog: ToolCatalogSnapshot,
    ) -> ResearchPlanDraft:
        raise ProviderUnavailableError("MODEL_PROVIDER_NOT_CONFIGURED")


class BlockedModelReasoningProvider:
    metadata = ReasoningProviderMetadata(
        provider_name="unconfigured-model-reasoner",
        provider_version="model-reasoner-v1",
        provider_type=ReasoningProviderType.MODEL_PROVIDER,
        test_only=False,
        requires_network=False,
        uses_model=True,
    )

    def validate_configuration(self) -> ProviderHealth:
        return ProviderHealth(
            status=ProviderHealthStatus.BLOCKED,
            code="MODEL_PROVIDER_NOT_CONFIGURED",
        )

    def propose_claims(
        self,
        evidence: EvidenceLedgerView,
        policy: ResearchPolicyRecord,
    ) -> tuple[ResearchClaimDraft, ...]:
        raise ProviderUnavailableError("MODEL_PROVIDER_NOT_CONFIGURED")


def create_production_planner() -> PlannerProvider:
    return DeterministicPlannerProvider()


def create_production_reasoner() -> ReasoningProvider:
    return DeterministicReasoningProvider()
