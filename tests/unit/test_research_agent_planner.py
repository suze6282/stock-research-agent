from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from stock_research_agent.domain.research_agent import planning
from stock_research_agent.domain.research_agent.enums import (
    ResearchMode,
    ResearchSection,
    ResearchType,
)
from stock_research_agent.domain.research_agent.plan_validation import (
    ResearchPlanValidator,
)
from stock_research_agent.domain.research_agent.policies import (
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import ResearchRequestRecord
from stock_research_agent.domain.research_agent.tool_catalog import (
    build_tool_catalog_snapshot,
)
from stock_research_agent.tools.registry import create_tool_metadata_registry

CATALOG = build_tool_catalog_snapshot(create_tool_metadata_registry())
POLICY = build_controlled_offline_policy()
NOW = datetime(2026, 7, 23, 4, 5, 6, tzinfo=UTC)


def _planner() -> object:
    assert hasattr(planning, "DeterministicTemplatePlanner")
    return planning.DeterministicTemplatePlanner()


def _request(research_type: ResearchType) -> ResearchRequestRecord:
    return ResearchRequestRecord(
        security_query="601138.SH",
        research_type=research_type,
        snapshot_id=UUID("22222222-2222-4222-8222-222222222222"),
        research_as_of_time=NOW,
        requested_sections=tuple(ResearchSection),
        policy_version=POLICY.version,
        planner_version="deterministic-template-v1",
        research_mode=ResearchMode.REAL_RESEARCH,
        id=UUID("44444444-4444-4444-8444-444444444444"),
        resolved_security_id=UUID("11111111-1111-4111-8111-111111111111"),
        normalized_security_query="601138.SH",
        tool_catalog_version=CATALOG.catalog_version,
        tool_catalog_checksum=CATALOG.catalog_checksum,
        request_checksum="b" * 64,
        created_at=NOW,
    )


@pytest.mark.parametrize("research_type", tuple(ResearchType))
def test_every_research_type_generates_a_valid_finite_plan(
    research_type: ResearchType,
) -> None:
    planner = _planner()
    request = _request(research_type)

    first = planner.create_plan(request, POLICY, CATALOG)
    second = planner.create_plan(request, POLICY, CATALOG)
    validated = ResearchPlanValidator().validate(first, POLICY, CATALOG)

    assert first == second
    assert planning.plan_checksum(first) == validated.plan_checksum
    assert len(first.steps) <= POLICY.max_steps
    assert tuple(step.step_index for step in first.steps) == tuple(range(len(first.steps)))


def test_full_research_package_is_exactly_12_approved_steps() -> None:
    plan = _planner().create_plan(
        _request(ResearchType.FULL_RESEARCH_PACKAGE),
        POLICY,
        CATALOG,
    )

    assert len(plan.steps) == 12
    assert tuple(step.tool_name for step in plan.steps if step.tool_name is not None) == (
        "get_data_snapshot",
        "get_financial_periods",
        "get_normalized_financial_facts",
        "get_financial_metrics",
        "get_metric_lineage",
        "get_corporate_actions",
        "search_document_chunks",
    )
    document_step = next(step for step in plan.steps if step.tool_name == "search_document_chunks")
    assert document_step.input_binding == {"query_template": "company_disclosures_bilingual-v1"}
    assert document_step.fanout_limit == 1


def test_planner_rejects_version_or_catalog_drift() -> None:
    planner = _planner()
    request = _request(ResearchType.COMPANY_OVERVIEW)

    with pytest.raises(ValueError, match="PLANNER_VERSION_MISMATCH"):
        planner.create_plan(
            request.model_copy(update={"planner_version": "other-planner-v1"}),
            POLICY,
            CATALOG,
        )
    with pytest.raises(ValueError, match="TOOL_CATALOG_VERSION_MISMATCH"):
        planner.create_plan(
            request.model_copy(update={"tool_catalog_version": "tool-catalog-v1:" + "f" * 64}),
            POLICY,
            CATALOG,
        )
