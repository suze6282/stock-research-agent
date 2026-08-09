from __future__ import annotations

import importlib
import importlib.util

from stock_research_agent.domain.research_agent.enums import ResearchStepType
from stock_research_agent.domain.research_agent.schemas import (
    ResearchPlanDraft,
    ResearchStepDefinition,
)

MODULE = "stock_research_agent.domain.research_agent.planning"
EXPECTED = "4f368c9f2d5c17d8648fdc1f5b27bbaa7c2a62738e1679b6d3b33ba22d13b4c5"


def _planning() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _draft(**step_updates: object) -> ResearchPlanDraft:
    step_values = {
        "step_index": 0,
        "step_key": "resolve_security",
        "step_type": ResearchStepType.RESOLVE_SECURITY,
        "title": "Resolve security",
        "required": True,
        "dependency_keys": (),
        "component_name": "security-resolution-v1",
        "input_binding": {},
        "fanout_limit": 1,
    }
    step_values.update(step_updates)
    return ResearchPlanDraft(
        planner_version="deterministic-template-v1",
        plan_version="research-plan-v1",
        tool_catalog_version="tool-catalog-v1:" + "a" * 64,
        steps=(ResearchStepDefinition.model_validate(step_values),),
    )


def test_plan_checksum_matches_independently_calculated_golden() -> None:
    planning = _planning()

    assert planning.plan_checksum(_draft()) == EXPECTED


def test_plan_checksum_is_stable_for_mapping_order_but_covers_semantics() -> None:
    planning = _planning()
    left = _draft(input_binding={"b": 2, "a": 1})
    right = _draft(input_binding={"a": 1, "b": 2})
    changed = _draft(input_binding={"a": 1, "b": 3})

    assert planning.plan_checksum(left) == planning.plan_checksum(right)
    assert planning.plan_checksum(left) != planning.plan_checksum(changed)
