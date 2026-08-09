"""Fail-closed validation for finite deterministic Research Plans."""

from __future__ import annotations

from stock_research_agent.domain.research_agent.enums import ResearchStepType
from stock_research_agent.domain.research_agent.planning import plan_checksum
from stock_research_agent.domain.research_agent.schemas import (
    ResearchPlanDraft,
    ResearchPolicyRecord,
    ResearchStepDefinition,
    ValidatedResearchPlan,
)
from stock_research_agent.domain.research_agent.tool_catalog import ToolCatalogSnapshot


class ResearchPlanValidationError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ResearchPlanValidator:
    def validate(
        self,
        draft: ResearchPlanDraft,
        policy: ResearchPolicyRecord,
        catalog: ToolCatalogSnapshot,
    ) -> ValidatedResearchPlan:
        if draft.tool_catalog_version != catalog.catalog_version:
            self._reject("TOOL_CATALOG_VERSION_MISMATCH")
        if len(draft.steps) > policy.max_steps:
            self._reject("STEP_BUDGET_EXCEEDED")

        keys = tuple(step.step_key for step in draft.steps)
        if len(set(keys)) != len(keys):
            self._reject("DUPLICATE_STEP_KEY")
        if tuple(step.step_index for step in draft.steps) != tuple(range(len(draft.steps))):
            self._reject("NON_CONTIGUOUS_STEP_INDEX")

        step_types = {step.step_type for step in draft.steps}
        if ResearchStepType.RESOLVE_SECURITY not in step_types:
            self._reject("REQUIRED_IDENTITY_STEP_MISSING")
        if ResearchStepType.LOAD_SNAPSHOT not in step_types:
            self._reject("REQUIRED_SNAPSHOT_STEP_MISSING")

        by_key = {step.step_key: step for step in draft.steps}
        for step in draft.steps:
            if (step.tool_name is None) == (step.component_name is None):
                self._reject("INVALID_STEP_TARGET")
            if step.tool_name is None and step.tool_version is not None:
                self._reject("INVALID_STEP_TARGET")
            if step.tool_name is not None and step.tool_version is None:
                self._reject("INVALID_STEP_TARGET")
            if step.step_key in step.dependency_keys:
                self._reject("SELF_STEP_DEPENDENCY")
            if any(key not in by_key for key in step.dependency_keys):
                self._reject("UNKNOWN_STEP_DEPENDENCY")

        self._reject_cycles(draft.steps, by_key)
        self._validate_tools(draft.steps, policy, catalog)
        self._require_order(
            draft.steps,
            by_key,
            ResearchStepType.BUILD_CLAIMS,
            ResearchStepType.VALIDATE_EVIDENCE,
            "INVALID_CLAIM_BUILD_ORDER",
        )
        self._require_order(
            draft.steps,
            by_key,
            ResearchStepType.VALIDATE_CLAIMS,
            ResearchStepType.BUILD_CLAIMS,
            "INVALID_CLAIM_VALIDATION_ORDER",
        )
        self._require_order(
            draft.steps,
            by_key,
            ResearchStepType.ASSEMBLE_PACKAGE,
            ResearchStepType.VALIDATE_CLAIMS,
            "INVALID_PACKAGE_ORDER",
        )
        return ValidatedResearchPlan(
            **draft.model_dump(mode="python"),
            plan_checksum=plan_checksum(draft),
        )

    def _validate_tools(
        self,
        steps: tuple[ResearchStepDefinition, ...],
        policy: ResearchPolicyRecord,
        catalog: ToolCatalogSnapshot,
    ) -> None:
        catalog_keys = {(entry.tool_name, entry.tool_version): entry for entry in catalog.entries}
        allowed = {(item.tool_name, item.tool_version) for item in policy.allowed_tools}
        denied = {(item.tool_name, item.tool_version) for item in policy.denied_tools}
        for step in steps:
            if step.tool_name is None or step.tool_version is None:
                continue
            key = (step.tool_name, step.tool_version)
            if key not in catalog_keys:
                self._reject("TOOL_NOT_IN_CATALOG")
            if key not in allowed or key in denied:
                self._reject("TOOL_NOT_ALLOWED_BY_POLICY")

    def _reject_cycles(
        self,
        steps: tuple[ResearchStepDefinition, ...],
        by_key: dict[str, ResearchStepDefinition],
    ) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(key: str) -> None:
            if key in visiting:
                self._reject("CYCLIC_PLAN")
            if key in visited:
                return
            visiting.add(key)
            for dependency in by_key[key].dependency_keys:
                visit(dependency)
            visiting.remove(key)
            visited.add(key)

        for step in steps:
            visit(step.step_key)

    def _require_order(
        self,
        steps: tuple[ResearchStepDefinition, ...],
        by_key: dict[str, ResearchStepDefinition],
        target_type: ResearchStepType,
        required_ancestor_type: ResearchStepType,
        code: str,
    ) -> None:
        targets = tuple(step for step in steps if step.step_type is target_type)
        ancestors = {step.step_key for step in steps if step.step_type is required_ancestor_type}
        if len(targets) != 1 or len(ancestors) != 1:
            self._reject(code)
        target = targets[0]
        if not self._has_ancestor(target, ancestors, by_key, set()):
            self._reject(code)

    def _has_ancestor(
        self,
        step: ResearchStepDefinition,
        required_keys: set[str],
        by_key: dict[str, ResearchStepDefinition],
        visited: set[str],
    ) -> bool:
        for key in step.dependency_keys:
            if key in required_keys:
                return True
            if key not in visited:
                visited.add(key)
                if self._has_ancestor(by_key[key], required_keys, by_key, visited):
                    return True
        return False

    @staticmethod
    def _reject(code: str) -> None:
        raise ResearchPlanValidationError(code)
