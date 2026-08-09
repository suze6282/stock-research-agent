from __future__ import annotations

import importlib
import importlib.util

import pytest

from stock_research_agent.domain.research_agent.enums import ResearchStepType
from stock_research_agent.domain.research_agent.policies import (
    build_controlled_offline_policy,
)
from stock_research_agent.domain.research_agent.schemas import (
    ResearchPlanDraft,
    ResearchStepDefinition,
)
from stock_research_agent.domain.research_agent.tool_catalog import (
    build_tool_catalog_snapshot,
)
from stock_research_agent.tools.registry import create_tool_metadata_registry

MODULE = "stock_research_agent.domain.research_agent.plan_validation"
CATALOG = build_tool_catalog_snapshot(create_tool_metadata_registry())
POLICY = build_controlled_offline_policy()


def _validation() -> object:
    assert importlib.util.find_spec(MODULE) is not None
    return importlib.import_module(MODULE)


def _step(
    index: int,
    key: str,
    step_type: ResearchStepType,
    dependencies: tuple[str, ...],
    *,
    tool_name: str | None = None,
    component_name: str | None = None,
) -> ResearchStepDefinition:
    return ResearchStepDefinition(
        step_index=index,
        step_key=key,
        step_type=step_type,
        title=key.replace("_", " ").title(),
        required=True,
        dependency_keys=dependencies,
        tool_name=tool_name,
        tool_version="1.0.0" if tool_name else None,
        component_name=component_name,
        input_binding={},
        fanout_limit=1,
    )


def _valid_steps() -> tuple[ResearchStepDefinition, ...]:
    return (
        _step(
            0,
            "resolve_security",
            ResearchStepType.RESOLVE_SECURITY,
            (),
            component_name="security-resolution-v1",
        ),
        _step(
            1,
            "load_snapshot",
            ResearchStepType.LOAD_SNAPSHOT,
            ("resolve_security",),
            tool_name="get_data_snapshot",
        ),
        _step(
            2,
            "collect_evidence",
            ResearchStepType.QUERY_STRUCTURED_DATA,
            ("load_snapshot",),
            tool_name="list_snapshot_items",
        ),
        _step(
            3,
            "validate_evidence",
            ResearchStepType.VALIDATE_EVIDENCE,
            ("collect_evidence",),
            component_name="evidence-ledger-v1",
        ),
        _step(
            4,
            "build_claims",
            ResearchStepType.BUILD_CLAIMS,
            ("validate_evidence",),
            component_name="deterministic-claim-builder-v1",
        ),
        _step(
            5,
            "validate_claims",
            ResearchStepType.VALIDATE_CLAIMS,
            ("build_claims",),
            component_name="claim-support-v1",
        ),
        _step(
            6,
            "assemble_package",
            ResearchStepType.ASSEMBLE_PACKAGE,
            ("validate_claims",),
            component_name="research-package-v1",
        ),
    )


def _draft(steps: tuple[ResearchStepDefinition, ...]) -> ResearchPlanDraft:
    return ResearchPlanDraft(
        planner_version="deterministic-template-v1",
        plan_version="research-plan-v1",
        tool_catalog_version=CATALOG.catalog_version,
        steps=steps,
    )


def test_valid_finite_dag_returns_checksum_without_repair() -> None:
    validation = _validation()
    draft = _draft(_valid_steps())

    result = validation.ResearchPlanValidator().validate(draft, POLICY, CATALOG)

    assert result.steps == draft.steps
    assert len(result.plan_checksum) == 64


def _invalid_cases() -> tuple[tuple[ResearchPlanDraft, str], ...]:
    valid = list(_valid_steps())
    duplicate_key = valid.copy()
    duplicate_key[1] = duplicate_key[1].model_copy(update={"step_key": "resolve_security"})
    non_contiguous = valid.copy()
    non_contiguous[2] = non_contiguous[2].model_copy(update={"step_index": 9})
    unknown_dependency = valid.copy()
    unknown_dependency[2] = unknown_dependency[2].model_copy(
        update={"dependency_keys": ("missing",)}
    )
    self_dependency = valid.copy()
    self_dependency[2] = self_dependency[2].model_copy(
        update={"dependency_keys": ("collect_evidence",)}
    )
    cycle = valid.copy()
    cycle[1] = cycle[1].model_copy(update={"dependency_keys": ("collect_evidence",)})
    cycle[2] = cycle[2].model_copy(update={"dependency_keys": ("load_snapshot",)})
    missing_identity = tuple(
        step.model_copy(update={"step_index": index}) for index, step in enumerate(valid[1:])
    )
    wrong_package_order = valid.copy()
    wrong_package_order[6] = wrong_package_order[6].model_copy(
        update={"dependency_keys": ("build_claims",)}
    )
    unknown_tool = valid.copy()
    unknown_tool[2] = unknown_tool[2].model_copy(update={"tool_name": "unknown_tool"})
    two_targets = valid.copy()
    two_targets[2] = two_targets[2].model_copy(update={"component_name": "also-a-component"})
    return (
        (_draft(tuple(duplicate_key)), "DUPLICATE_STEP_KEY"),
        (_draft(tuple(non_contiguous)), "NON_CONTIGUOUS_STEP_INDEX"),
        (_draft(tuple(unknown_dependency)), "UNKNOWN_STEP_DEPENDENCY"),
        (_draft(tuple(self_dependency)), "SELF_STEP_DEPENDENCY"),
        (_draft(tuple(cycle)), "CYCLIC_PLAN"),
        (_draft(missing_identity), "REQUIRED_IDENTITY_STEP_MISSING"),
        (_draft(tuple(wrong_package_order)), "INVALID_PACKAGE_ORDER"),
        (_draft(tuple(unknown_tool)), "TOOL_NOT_IN_CATALOG"),
        (_draft(tuple(two_targets)), "INVALID_STEP_TARGET"),
        (
            _draft(tuple(valid)).model_copy(
                update={"tool_catalog_version": "tool-catalog-v1:" + "f" * 64}
            ),
            "TOOL_CATALOG_VERSION_MISMATCH",
        ),
    )


@pytest.mark.parametrize(("draft", "code"), _invalid_cases())
def test_invalid_plan_is_rejected_without_repair(
    draft: ResearchPlanDraft,
    code: str,
) -> None:
    validation = _validation()

    with pytest.raises(validation.ResearchPlanValidationError) as raised:
        validation.ResearchPlanValidator().validate(draft, POLICY, CATALOG)

    assert raised.value.code == code
