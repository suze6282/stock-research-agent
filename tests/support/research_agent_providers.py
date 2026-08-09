"""Scripted provider doubles that cannot enter production composition."""

from stock_research_agent.domain.research_agent.enums import (
    PlannerType,
    ProviderHealthStatus,
    ReasoningProviderType,
)
from stock_research_agent.domain.research_agent.schemas import (
    PlannerProviderMetadata,
    ProviderHealth,
    ReasoningProviderMetadata,
)


class ScriptedTestPlanner:
    metadata = PlannerProviderMetadata(
        provider_name="scripted-test-planner",
        provider_version="scripted-test-planner-v1",
        provider_type=PlannerType.SCRIPTED_TEST,
        test_only=True,
        requires_network=False,
        uses_model=False,
    )

    def __init__(self, plan: object) -> None:
        self._plan = plan

    def validate_configuration(self) -> ProviderHealth:
        return ProviderHealth(
            status=ProviderHealthStatus.TEST_ONLY,
            code="SCRIPTED_TEST_ONLY",
        )

    def create_plan(self, *_args: object) -> object:
        return self._plan


class ScriptedTestReasoner:
    metadata = ReasoningProviderMetadata(
        provider_name="scripted-test-reasoner",
        provider_version="scripted-test-reasoner-v1",
        provider_type=ReasoningProviderType.SCRIPTED_TEST,
        test_only=True,
        requires_network=False,
        uses_model=False,
    )

    def __init__(self, claims: tuple[object, ...]) -> None:
        self._claims = claims

    def validate_configuration(self) -> ProviderHealth:
        return ProviderHealth(
            status=ProviderHealthStatus.TEST_ONLY,
            code="SCRIPTED_TEST_ONLY",
        )

    def propose_claims(self, *_args: object) -> tuple[object, ...]:
        return self._claims
